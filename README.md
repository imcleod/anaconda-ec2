Run the Anaconda installer in EC2
=================================

This is an attempt to collect some code that launches Anaconda based installs inside of EBS backed
images in EC2.  This takes advantage of the ability to use pvgrub to launch EBS backed images using
kernels and ramdisks contained in the EBS volume.

This project is related to my work to run installers natively inside of the OpenStack Nova component:

https://github.com/redhat-openstack/image-building-poc/


