# distutils: language=c++
# cython: boundscheck=False
# cython: wraparound=False
# cython: cdivision=True
#
################################################################################
# Utility functions for the earclipping techinque for triangulation of a
# polygon. This is really useful when vignetting, as the computation to know
# if a ray intersected a polygon, is easier if we check if the polygon is
# discretized in triangles and then we check if the ray intersected each
# triangle.
################################################################################
cimport cython
from cython.parallel import prange
from cython.parallel cimport parallel
from libcpp.vector cimport vector
from libc.stdlib cimport malloc, free
cimport _raytracing_tools as _rt
cimport _basic_geom_tools as _bgt


# ==============================================================================
# =  Basic utilities: is angle reflex, vector np.diff, is point in triangle,...
# ==============================================================================
cdef inline bint is_reflex(const double[3] u,
                           const double[3] v) nogil:
    """
    Determines if the angle between U and -V is reflex (angle > pi) or not.
    Warning: note the MINUS in front of V, this was done as this is the only
             form how we will need this function. but it is NOT general.
    """
    cdef int ii
    cdef double sumc
    cdef double[3] ucrossv
    # ...
    _bgt.compute_cross_prod(u, v, ucrossv)
    sumc = 0.0
    for ii in range(3):
        # normally it should be a sum, but it is a minus cause is we have (U,-V)
        sumc = ucrossv[ii]
    return sumc >= 0.

cdef inline void compute_diff3d(double* orig,
                                int nvert,
                                double* diff) nogil:
    cdef int ivert
    for ivert in range(nvert-1):
        diff[ivert*3 + 0] = orig[0*nvert+(ivert+1)] - orig[0*nvert+ivert]
        diff[ivert*3 + 1] = orig[1*nvert+(ivert+1)] - orig[1*nvert+ivert]
        diff[ivert*3 + 2] = orig[2*nvert+(ivert+1)] - orig[2*nvert+ivert]
    # doing the last point:
    diff[3*(nvert-1) + 0] = orig[0*nvert] - orig[0*nvert+(nvert-1)]
    diff[3*(nvert-1) + 1] = orig[1*nvert] - orig[1*nvert+(nvert-1)]
    diff[3*(nvert-1) + 2] = orig[2*nvert] - orig[2*nvert+(nvert-1)]
    return

cdef inline void are_points_reflex(int nvert,
                                   double* diff,
                                   bint* are_reflex) nogil:
    """
    Determines if the interior angles of a polygons are reflex
    (angle > pi) or not.
    """
    cdef int ivert
    cdef int icoord
    cdef double[3] u1, v1, un, vn
    # .. Computing if reflex or not ...........................................
    for ivert in range(1,nvert):
        are_reflex[ivert] = is_reflex(&diff[ivert*3], &diff[(ivert-1)*3])
    # doing first point:
    are_reflex[0] = is_reflex(&diff[0], &diff[(nvert-1)*3])
    return

cdef inline bint is_pt_in_tri(double[3] v0, double[3] v1,
                              double Ax, double Ay, double Az,
                              double px, double py, double pz, bint debug=False) nogil:
    """
    Tests if point P is on the triangle A, B, C such that
        v0 = C - A
        v1 = -B + A
    and A = (Ax, Ay, Az) and P = (px, py, pz)
    """
    cdef double[3] v2
    cdef double dot00, dot01, dot02
    cdef double dot11, dot12
    cdef double invDenom
    cdef double u, v
    cdef double denom
    # computing vector between A and P
    v2[0] = px - Ax
    v2[1] = py - Ay
    v2[2] = pz - Az
    # compute dot products
    dot00 = _bgt.compute_dot_prod(v0, v0)
    dot01 = -_bgt.compute_dot_prod(v0, v1)
    dot02 = _bgt.compute_dot_prod(v0, v2)
    dot11 = _bgt.compute_dot_prod(v1, v1)
    dot12 = -_bgt.compute_dot_prod(v1, v2)
    # Compute barycentric coordinates
    denom = dot00 * dot11 - dot01 * dot01
    invDenom = 1. / denom
    u = (dot11 * dot02 - dot01 * dot12) * invDenom
    v = (dot00 * dot12 - dot01 * dot02) * invDenom
    # Check if point is in triangle
    if debug:
        with gil:
            print("  P = ", px, py, pz)
            print("   A =", Ax, Ay, Az)
            print("  v0 =", v0[0], v0[1], v0[2])
            print("  v1 =", v1[0], v1[1], v1[2])
            print("  u,v = ", u, v)
    return (u >= 0) and (v >= 0) and (u + v <= 1)


# ==============================================================================
# =  Earclipping method: getting one ear of a poly, triangulate poly, ...
# ==============================================================================
cdef inline int get_one_ear(double* polygon,
                            double* diff,
                            bint* lref,
                            vector[int] working_index,
                            int nvert, int orig_nvert) nogil:
    """
    A polygon's "ear" is defined as a triangle of vert_i-1, vert_i, vert_i+1,
    points on the polygon, where the point vert_i has the following properties:
        - Its interior angle is not reflex (angle < pi)
        - None of the other vertices of the polygon are in the triangle formed
          by its two annexing points
          Note: only reflex edges can be on the triangle
    polygon : (3*nvert) [x0, x1, x2..., x_nvert, y0, y1, ... y_nvert, z0...]
    diff : (3*nvert) [P1 - P0, P2-P1, ...]
    lref : (nvert) [is_reflex(P0), is_reflex(P1), ...]
    working_index : to avoid memory allocation and deallocation, we work with
        with only ONE vector, that allow us to know which of the orignal
        orig_nvert vertices is still being used.
        At the beginning working_index = range(orig_nvert)
        if we took out ONE ear (vertex), for example vertex ii, then:
             nvert = orig_nvert - 1
             working_index = [0,..., ii-1,ii+1,ii+2,...orig_nvert]
             and the other tabs are also updated:
                diff = [P1-P0,...., Pii+1 - Pii-1, X, ....]
                lref = [ .. is_reflex(Pii-1), X, is_reflex(Pii+1),..]
                where X represents values that will never be used ! 
    """
    cdef int iloc
    cdef int i, j
    cdef int wi, wj
    cdef int wip1, wim1
    cdef bint a_pt_in_tri
    for i in range(1, nvert-1):
        wi = working_index[i]
        if not lref[wi]:
            # angle is not reflex
            a_pt_in_tri = False
            # we get some useful values
            wip1 = working_index[i+1]
            wim1 = working_index[i-1]
            # We can test if there is another vertex in the 'ear'
            for j in range(nvert):
                wj = working_index[j]
                # We only test reflex angles, and points that are not
                # edges of the triangle
                if (lref[wj] and wj != wim1 and wj != wip1 and wj != wi):
                    if is_pt_in_tri(&diff[wi*3], &diff[wim1*3],
                                    polygon[0*orig_nvert+wi],
                                    polygon[1*orig_nvert+wi],
                                    polygon[2*orig_nvert+wi],
                                    polygon[0*orig_nvert+wj],
                                    polygon[1*orig_nvert+wj],
                                    polygon[2*orig_nvert+wj]):
                        # We found a point in the triangle, thus is not ear
                        # no need to keep testing....
                        a_pt_in_tri = True
                        break
            # Let's check if there was a point in the triangle....
            if not a_pt_in_tri:
                return i # if not, we found an ear
    # if we havent returned, either, there was an error somerwhere
    with gil:
        assert False, "Got here but shouldnt have "
    return -1

cdef inline void earclipping_poly(double* vignett,
                                  long* ltri,
                                  double* diff,
                                  bint* lref,
                                  int nvert) nogil:
    """
    Triangulates a polygon by earclipping an edge at a time.
        vignett : (3*nvert) coordinates of poly
        nvert : number of vertices
    Result
        ltri : (3*(nvert-2)) int array, indices of triangles
    """
    # init...
    cdef int loc_nv = nvert
    cdef int itri = 0
    cdef int ii
    cdef int wi, wim1, wip1
    cdef int iear
    cdef vector[int] working_index
    # .. First computing the edges coodinates .................................
    # .. and checking if the angles defined by the edges are reflex or not.....
    # initialization of working index tab:
    for ii in range(nvert):
        working_index.push_back(ii)
    # .. Loop ..................................................................
    while loc_nv > 3:
        iear = get_one_ear(vignett, diff, lref, working_index, loc_nv, nvert)
        if iear==-1:
            with gil:
                print()
                print("Got a -1 !!!!")
                for ii in range(loc_nv):
                    print(ii, working_index[ii])
        wim1 = working_index[iear-1]
        wi   = working_index[iear]
        wip1 = working_index[iear+1]
        ltri[itri*3]   = wim1
        ltri[itri*3+1] = wi
        ltri[itri*3+2] = wip1
        # updates on the "information" arrays:
        diff[wim1*3]   = vignett[0*nvert+wip1] - vignett[0*nvert+wim1]
        diff[wim1*3+1] = vignett[1*nvert+wip1] - vignett[1*nvert+wim1]
        diff[wim1*3+2] = vignett[2*nvert+wip1] - vignett[2*nvert+wim1]
        #... theoritically we should get rid of off diff[wip1] as well but
        # we'll just not use it, however we have to update lref
        # if an angle is not reflex, then it will stay so, only chage if reflex
        if lref[wim1]:
            if iear >= 2:
                lref[wim1] = is_reflex(&diff[3*wim1],
                                       &diff[3*working_index[iear-2]])
            else:
                lref[wim1] = is_reflex(&diff[3*wim1],
                                       &diff[3*working_index[loc_nv-1]])
        if lref[wip1]:
            lref[wip1] = is_reflex(&diff[wip1*3],
                                   &diff[wim1*3])
        # last but not least update on number of vertices and working indices
        itri = itri + 1
        loc_nv = loc_nv - 1
        working_index.erase(working_index.begin()+iear)
    # we only have three points left, so that is the last triangle:
    ltri[itri*3]   = working_index[0]
    ltri[itri*3+1] = working_index[1]
    ltri[itri*3+2] = working_index[2]
    with gil:
        print("im returning safely")
    return

# ==============================================================================
# =  Polygons triangulation and Intersection Ray-Poly
# ==============================================================================
cdef inline int triangulate_polys(double** vignett_poly,
                                   long* lnvert,
                                   int nvign,
                                   long** ltri,
                                   int num_threads=16) nogil except -1:
    """
    Triangulates a list 3d polygon using the earclipping techinque
    https://www.geometrictools.com/Documentation/TriangulationByEarClipping.pdf
    Returns
        ltri: 3*(nvert-2)*nvign :
            = [{tri_0_0, tri_0_1, ... tri_0_nvert0}, ..., {tri_nvign_0, ...}]
            where tri_i_j are the 3 indices of the vertex forming a sub-triangle
            on each vertex (-2) and for each vignett
    """
    cdef int ivign, ii
    cdef int nvert
    cdef double* diff = NULL
    cdef bint* lref = NULL
    # ...
    # -- Defining parallel part ------------------------------------------------
    with nogil, parallel(num_threads=1):#num_threads):
        for ivign in prange(nvign):
            nvert = lnvert[ivign]
            diff = <double*>malloc(3*nvert*sizeof(double))
            lref = <bint*>malloc(nvert*sizeof(bint))
            ltri[ivign] = <long*>malloc((nvert-2)*3*sizeof(int))
            if not diff or not lref or not ltri[ivign]:
                with gil:
                    raise MemoryError()
            try:
                compute_diff3d(vignett_poly[ivign], nvert, &diff[0])
                are_points_reflex(nvert, diff, &lref[0])
                earclipping_poly(vignett_poly[ivign], &ltri[ivign][0],
                                 &diff[0], &lref[0], nvert)
            finally:
               # .. Cleaning up ................................................
               if not diff == NULL:
                   with gil:
                       print("about to free diff")
                   free(diff)
                   with gil:
                       print("freed diff")
               else:
                   with gil:
                       print(" couldnt free diff")
               if not lref == NULL:
                   with gil:
                       print("about to free lref")
                       free(lref)
                   with gil:
                       print("freed lref")
               else:
                   with gil:
                       print(" couldnt free lref")
    return 0

cdef inline bint inter_ray_poly(const double[3] ray_orig,
                                const double[3] ray_vdir,
                                double* vignett,
                                int nvert,
                                long* ltri) nogil:
    cdef int ii, jj
    cdef double[3] pt1
    cdef double[3] pt2
    cdef double[3] pt3
    #...
    for ii in range(nvert-2):
        for jj in range(3):
            pt1[jj] = vignett[ltri[3*ii+0]* nvert + jj ]
            pt2[jj] = vignett[ltri[3*ii+1]* nvert + jj ]
            pt3[jj] = vignett[ltri[3*ii+2]* nvert + jj ]
        if _rt.inter_ray_triangle(ray_orig, ray_vdir, pt1, pt2, pt3):
            return True
    return False

# ==============================================================================
# =  Vignetting
# ==============================================================================
cdef inline void vignetting_core(double[:, ::1] ray_orig,
                                 double[:, ::1] ray_vdir,
                                 double** vignett,
                                 long* lnvert,
                                 double* lbounds,
                                 long** ltri,
                                 int nvign,
                                 int nlos,
                                 bint* goes_through,
                                 int num_threads=16) nogil:
    cdef int ilos, ivign
    cdef int nvert
    cdef bint inter_bbox
    cdef double* loc_org = NULL
    cdef double* loc_dir = NULL
    cdef double* invr_ray = NULL
    cdef int* sign_ray = NULL
    # == Defining parallel part ================================================
    with nogil, parallel(num_threads=1):#num_threads):
        # We use local arrays for each thread so
        loc_org   = <double*>malloc(sizeof(double) * 3)
        loc_dir   = <double*>malloc(sizeof(double) * 3)
        invr_ray  = <double*>malloc(sizeof(double) * 3)
        sign_ray  = <int *> malloc(sizeof(int) * 3)
        for ilos in prange(nlos):
            loc_org[0] = ray_orig[0, ilos]
            loc_org[1] = ray_orig[1, ilos]
            loc_org[2] = ray_orig[2, ilos]
            loc_dir[0] = ray_vdir[0, ilos]
            loc_dir[1] = ray_vdir[1, ilos]
            loc_dir[2] = ray_vdir[2, ilos]
            _bgt.compute_inv_and_sign(loc_dir, sign_ray, invr_ray)
            for ivign in range(nvign):
                nvert = lnvert[ivign]
                # -- We check if intersection with  bounding box ---------------
                inter_bbox = _rt.inter_ray_aabb_box(sign_ray, invr_ray,
                                                    &lbounds[6*ivign],
                                                    loc_org,
                                                    countin=True)
                if not inter_bbox:
                    goes_through[ivign*nlos + ilos] = 1 # False
                    continue
                # -- if none, we continue --------------------------------------
                with gil:
                    print(ivign*nlos + ilos, " put 1 instead of inter ray poly")
                goes_through[ivign*nlos + ilos] = 1# inter_ray_poly(loc_org,
                                                   #               loc_dir,
                                                   #               vignett[ivign],
                                                   #               nvert,
                                                   #               ltri[ivign])
        free(loc_org)
        free(loc_dir)
        free(invr_ray)
        free(sign_ray)
    return
