install
url --url=http://mirror.stanford.edu/yum/pub/centos/6.4/os/x86_64/
# Needed for cloud-init
repo --name="EPEL-6" --baseurl="http://mirrors.kernel.org/fedora-epel/6/x86_64/"
graphical
vnc --password=${adminpw}
key --skip
keyboard us
lang en_US.UTF-8
skipx
network --device eth0 --bootproto dhcp
rootpw ${adminpw}
firewall --disabled
authconfig --enableshadow --enablemd5
selinux --enforcing
timezone --utc America/New_York
bootloader --location=mbr --append="console=tty0 console=ttyS0,115200"
zerombr yes
clearpart --all --drives=xvde

part /boot --fstype ext3 --size=200 --ondisk=xvde
part pv.2 --size=1 --grow --ondisk=xvde
volgroup VolGroup00 --pesize=32768 pv.2
#logvol swap --fstype swap --name=LogVol01 --vgname=VolGroup00 --size=768 --grow --maxsize=1536
logvol / --fstype ext4 --name=LogVol00 --vgname=VolGroup00 --size=1024 --grow
poweroff

%packages
@base
cloud-init
%end

%post

# EC2 pvgrub looks /boot/menu.lst in the first partition
# That results in this somewhat odd setup
# Thankfully, RHEL6 uses grub legacy so the config file should work with just a symlink
mkdir -p /boot/boot/grub
ln -s ../../grub/grub.conf /boot/boot/grub/menu.lst

# RHEL6 is unforgiving about changed MAC addresses - deal with that here:
rm -f /etc/udev/rules.d/70-persistent-net.rules || /bin/true
grep -v HWADDR /etc/sysconfig/network-scripts/ifcfg-eth0 > /etc/sysconfig/network-scripts/ifcfg-eth0.new
mv -f /etc/sysconfig/network-scripts/ifcfg-eth0.new /etc/sysconfig/network-scripts/ifcfg-eth0
chmod 644 /etc/sysconfig/network-scripts/ifcfg-eth0

%end
