
import numpy as np
import scipy.interpolate as scpinterp

# ###############################################
# ###############################################
#           CrystalBragg
# ###############################################
# ###############################################

# ###############################################
#           Coordinates transforms
# ###############################################

def checkformat_vectang(Z, nn, frame_cent, frame_ang):
    # Check / format inputs
    nn = np.atleast_1d(nn).ravel()
    assert nn.size == 3
    nn = nn / np.linalg.norm(nn)

    Z = float(Z)

    frame_cent = np.atleast_1d(frame_cent).ravel()
    assert frame_cent.size == 2
    frame_ang = float(frame_ang)

    return Z, nn, frame_cent, frame_ang


def get_e1e2_detectorplane(nn, nIn):
    e1 = np.cross(nn, nIn)
    e1n = np.linalg.norm(e1)
    if e1n < 1.e-10:
        e1 = np.array([nIn[2], -nIn[1], 0.])
        e1n = np.linalg.norm(e1)
    e1 = e1 / e1n
    e2 = np.cross(nn, e1)
    e2 = e2 / np.linalg.norm(e2)
    return e1, e2

def get_bragg_from_lamb(lamb, d, n=1):
    """ n*lamb = 2d*sin(bragg) """
    bragg= np.full(lamb.shape, np.nan)
    sin = n*lamb/(2.*d)
    indok = np.abs(sin) <= 1.
    bragg[indok] = np.arcsin(sin[indok])
    return bragg

def get_lamb_from_bragg(bragg, d, n=1):
    """ n*lamb = 2d*sin(bragg) """
    return 2*d*np.sin(bragg) / n

def calc_xixj_from_braggangle(Z, nIn,
                              frame_cent, frame_ang,
                              nn, e1, e2,
                              bragg, angle):
        # Deduce key angles
        costheta = np.cos(np.pi/2 - bragg)
        sintheta = np.sin(np.pi/2 - bragg)
        cospsi = np.sum(nIn*nn)
        sinpsi = np.sum(np.cross(nIn, nn)*e1)

        # Deduce ellipse parameters
        cos2sin2 = costheta**2 - sinpsi**2
        x2C = Z * sinpsi * sintheta**2 / cos2sin2
        a = Z * sintheta * cospsi / np.sqrt(cos2sin2)
        b = Z * sintheta * cospsi * costheta / cos2sin2

        # Get radius from axis => x1, x2 => xi, xj
        asin2bcos2 = (b[None,:]**2*np.cos(angle[:,None])**2
                      + a[None,:]**2*np.sin(angle[:,None])**2)
        l = ((a[None,:]**2*x2C[None,:]*np.sin(angle[:,None])
              + a[None,:]*b[None,:]*np.sqrt(asin2bcos2 -
                                            x2C[None,:]**2*np.cos(angle[:,None])**2))
             / asin2bcos2)

        x1_frame = l*np.cos(angle[:,None]) - frame_cent[0]
        x2_frame = l*np.sin(angle[:,None]) - frame_cent[1]

        xi = x1_frame*np.cos(frame_ang) + x2_frame*np.sin(frame_ang)
        xj = -x1_frame*np.sin(frame_ang) + x2_frame*np.cos(frame_ang)
        return xi, xj

def calc_braggangle_from_xixj(xi, xj, Z, nn, frame_cent, frame_ang,
                              nIn, e1, e2):

        # We have e1, e2 => compute x1, x2
        x1 = (frame_cent[0]
              + xi[:,None]*np.cos(frame_ang)
              - xj[None,:]*np.sin(frame_ang))
        x2 = (frame_cent[1]
              + xi[:,None]*np.sin(frame_ang)
              + xj[None,:]*np.cos(frame_ang))

        # Deduce OM
        sca = Z + x1*np.sum(e1*nIn) + x2*np.sum(e2*nIn)
        norm = np.sqrt((Z*nIn[0] + x1*e1[0] + x2*e2[0])**2
                       + (Z*nIn[1] + x1*e1[1] + x2*e2[1])**2
                       + (Z*nIn[2] + x1*e1[2] + x2*e2[2])**2)
        bragg = np.pi/2 - np.arccos(sca/norm)

        # Get angle with respect to axis ! (not center)
        ang = np.arctan2(x2, x1)

        # costheta = np.cos(bragg)
        # sintheta = np.sin(bragg)
        # cospsi = np.sum(nIn*nn)
        # sinpsi = np.sum(np.cross(nIn, nn)*e1)
        # cos2sin2 = costheta**2 - sinpsi**2
        # x2C = Z * sinpsi * sintheta**2 / cos2sin2
        # ang = np.arctan2(x2-x2C, x1)

        return bragg, ang


# ###############################################
#           Spectral fit 2d - user-friendly
# ###############################################

def get_2dspectralfit_func(lambrest, deg=None, knots=None):

    lambrest = np.atleast_1d(lambrest).ravel()
    nlamb = lambrest.size
    knots = np.atleast_1d(knots).ravel()
    nknots = knots.size
    nbsplines = np.unique(knots).size - 1 + deg

    # Get 3 sets of bsplines for each lamb
    bsamp = scpinterp.BSpline(knots, np.ones((nbsplines,)), deg,
                              extrapolate=False, axis=0)
    bsshift = scpinterp.BSpline(knots, np.ones((nbsplines,)), deg,
                                  extrapolate=False, axis=0)
    bswidth = scpinterp.BSpline(knots, np.ones((nbsplines,)), deg,
                                  extrapolate=False, axis=0)

    # Define function
    def func(lamb, angle,
             camp=None, cwidth=None, cshift=None,
             lambrest=lambrest, knots=knots, deg=deg, nbsplines=nbsplines,
             mesh=True):
        nlamb = lambrest.size
        if camp is not None:
            assert camp.shape[0] == nbsplines
            bsamp = scpinterp.BSpline(knots, camp, deg,
                                      extrapolate=False, axis=0)
        if cwidth is not None:
            assert cwidth.shape[0] == nbsplines
            bswidth = scpinterp.BSpline(knots, cwidth, deg,
                                        extrapolate=False, axis=0)
        if cshift is not None:
            assert cshift.shape[0] == nbsplines
            bshift = scpinterp.BSpline(knots, cshift, deg,
                                       extrapolate=False, axis=0)
        assert angle.ndim in [1, 2]
        if mesh or angle.ndim == 2:
            lambrest = lambrest[None, None, :]
        else:
            lambrest = lambrest[None, :]

        if mesh:
            assert angle.ndim == lamb.ndim == 1
            # shape (lamb, angle, lines)
            return np.sum(bsamp(angle)[None,:,:]
                          * np.exp(-(lamb[:,None,None]
                                     - (lambrest
                                        + bshift(angle)[None,:,:]))**2
                                   /(bswidth(angle)[None,:,:]**2)), axis=-1)
        else:
            assert angle.shape == lamb.shape
            if angle.ndim == 2:
                lamb = lamb[:, :, None]
            else:
                lamb = lamb[:, None]
            # shape (lamb/angle, lines)
            return np.sum(bsamp(angle)
                          * np.exp(-(lamb
                                     - (lambrest
                                        + bshift(angle)))**2
                                   /(bswidth(angle)**2)), axis=-1)


    return func
