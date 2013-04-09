#!/usr/bin/python

import sys
from pvgrub_utils import generate_install_image

if len(sys.argv) != 3:
    print
    print "Create a pvgrub bootable image file for EC2"
    print
    print "usage: %s <ks_file> <image_file>" % sys.argv[0]
    print
    sys.exit(1)

generate_install_image(sys.argv[1], sys.argv[2])

