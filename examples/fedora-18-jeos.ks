url --url=http://mirror.pnl.gov/fedora/linux/releases/18/Fedora/x86_64/os/
# Without the Everything repo, we cannot install cloud-init
repo --name="fedora-everything" --baseurl=http://mirror.pnl.gov/fedora/linux/releases/18/Everything/x86_64/os/
install
graphical
vnc --password=changeme
keyboard us
lang en_US.UTF-8
skipx
network --device eth0 --bootproto dhcp
rootpw p@ssw0rd
firewall --disabled
authconfig --enableshadow --enablemd5
selinux --enforcing
timezone --utc America/New_York
bootloader --location=none
zerombr
clearpart --all --drives=xvda

#part biosboot --fstype=biosboot --size=1
part /boot --fstype ext2 --size=200 --ondisk=xvda
part pv.2 --size=1 --grow --ondisk=xvda
volgroup VolGroup00 --pesize=32768 pv.2
#logvol swap --fstype swap --name=LogVol01 --vgname=VolGroup00 --size= --grow --maxsize=1536
logvol / --fstype ext4 --name=LogVol00 --vgname=VolGroup00 --size=850 --grow
poweroff

bootloader --location=none

%packages
@core
cloud-init
%end

%post

#### Set up the image so that it can boot via pvgrub

# Details at http://docs.aws.amazon.com/AWSEC2/latest/UserGuide/UserProvidedkernels.html

# Note that Anaconda based installs such as this _must_ use the hd00 version of
# the pvgrub AKI.  That is, the version that assumes the root EBS device is at 
# /dev/xvda and is a disk image with a partition table, not a raw filesystem.

### Get the most recently installed kernel version
# This assumes, correctly as best I can tell, that rpm returns packages in the order they are installed
# This is, I think, a reasonable approach as it should prefer updates.
NUMBER_KERNELS=`rpm -q --queryformat "%{VERSION}-%{RELEASE}\n" kernel  | wc -l | tr -d '\n'`
LATEST_VER=`rpm -q --queryformat "%{VERSION}-%{RELEASE}.%{ARCH}|" kernel | cut -f $NUMBER_KERNELS -d "|" | tr -d '\n'`

# pvgrub looks for /boot/grub/menu.lst in the first partition on the EBS volume
# At this point in Anaconda , the first partition is mounted under /boot, so we need
# to create this somewhat odd looking path with an extra /boot on the front.
mkdir -p /boot/boot/grub

# Now write out a menu.lst that should boot the latest kernel
# The root is hard coded based on the details in the partition section above
cat <<EOF > /boot/boot/grub/menu.lst
# This file is for use with pv-grub; legacy grub is not installed in this image
default=0
timeout=0
#hiddenmenu
title Fedora-18-ec2 ($LATEST_VER)
        root (hd0,0)
        kernel /vmlinuz-$LATEST_VER ro root=/dev/mapper/VolGroup00-LogVol00
        initrd /initramfs-$LATEST_VER.img
EOF

%end
