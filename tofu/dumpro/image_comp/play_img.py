# -*- coding: utf-8 -*-
"""
Created on Wed Jun 12 09:55:06 2019

@author: Arpan Khandelwal
email; napraarpan@gmail.com
"""

# Built-in
import os

# Standard
import numpy as np

# More special
try:
    import cv2
except ImportError:
    print("Could not find opencv package. Try pip intall opencv-contrib-python")
    
    def play(im_path):
        """
        """
        
        #creating a list of all the files
        files = [f for f in os.listdir(im_path) if os.path.isfile(os.path.join(im_path,f))]    

        #sorting files according to names using lambda function
        #-4 is to remove the extension of the images i.e., .jpg
        files.sort(key = lambda x: int(x[5:-4]))
        #looping throuah all the file names in the list and converting them to image path
        
        for i in range(len(files)):
            #converting to path
            filename = im_path + files[i]
            
            img = cv2.imread(filename,cv2.IMREAD_UNCHANGED)
            
            cv2.imshow('Frame',img)
            if cv2.waitKey(25) & 0xFF == ord('q'): 
                break
        
        cv2.destroyAllWindows()
        
            