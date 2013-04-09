Run the Anaconda installer in EC2
=================================

This is an attempt to collect some code that launches Anaconda based installs inside of EBS backed
images in EC2.  This takes advantage of the ability to use pvgrub to launch EBS backed images using
kernels and ramdisks contained in the EBS volume.

This project is related to my work to run installers natively inside of the OpenStack Nova component:

https://github.com/redhat-openstack/image-building-poc/

This requires the boto EC2 bindings and libguestfs.  So, to start off with on Fedora or RHEL do this:

$ yum install python-libguestfs python-boto

It may require other things I have missed.  If so lemmie know.  

-Ian - imcleod@redhat.com


## Example

### Create a local disk image that will boot Anaconda via pvgrub

    $ ./pvgrub_image_from_ks.py ./examples/fedora-18-jeos.ks ./fedora_18.raw

For this step, the kickstart must contain a "url" line that points to a valid install
tree for the OS in question.  This URL will be used to extract the kernel and ramdisk
needed to bootstrap Anaconda.  Adding support for DVD ISO install sources is a potential
next step.

The extracted kernel and ramdisk are put into a disk image along with a valid pvgrub
menu.lst file.  This is all that is needed to launch Anaconda inside of an EC insance.


### Turn this image into an AMI

    $ ./ami_from_image_file.py <ec2_region> <ec2_key> <ec2_secret> ./fedora_18.raw

If successful this will return an AMI on a line that looks like this:

    Got AMI: ami-beefbeef

This AMI launches Anaconda and looks for a kickstart file at the EC2 user data URL.

### Launch this AMI, wait for the install to complete then capture the results as a new AMI

The next script will launch this AMI, pass the kickstart via user data and then wait
for the install to complete and the instance to shut down.  Once this is done it will
create a new AMI using the create image call from the EC2 API.

    $ ./install_on_ec2.py <ec2_region> <ec2_key> <ec2_secret> <ami_from_last_step> ./examples/fedora-18-jeos.ks <root_password>

Note that you do not need to use the same kickstart file for the first and last step.  
However, the OS version and architecture must match.  That is, if the initial ks.cfg
pointed to an F18 64 bit install source this last step will launch an F18 64 bit Anaconda
installer.

Once the install instance is running, the script above will report its public
DNS address.  The F18 example kickstart in this repo contains a "vnc" line to allow
you to watch the graphical installer as it is running.  To do this, run the following
command:

    $ vncviewer <public_hostname_from_above>:1

When asked for a password, use the same oneyou passed as <root_password> above.
The VNC session will close when the install is complete and the script will eventually
return an AMI.  This is the completed image.

