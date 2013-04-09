#!/usr/bin/python
#   Copyright (C) 2013 Red Hat, Inc.
#   Copyright (C) 2013 Ian McLeod <imcleod@redhat.com>
#
#   Licensed under the Apache License, Version 2.0 (the "License");
#   you may not use this file except in compliance with the License.
#   You may obtain a copy of the License at
#
#       http://www.apache.org/licenses/LICENSE-2.0
#
#   Unless required by applicable law or agreed to in writing, software
#   distributed under the License is distributed on an "AS IS" BASIS,
#   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#   See the License for the specific language governing permissions and
#   limitations under the License.

import guestfs
import ozutil
import re
import shutil
import sys
import logging
import os
import os.path
from tempfile import mkdtemp
from string import Template

def create_ext2_image(image_file, image_size=(1024*1024*200)):
    raw_fs_image=open(image_file,"w")
    raw_fs_image.truncate(image_size)
    raw_fs_image.close()

    g = guestfs.GuestFS()

    g.add_drive(image_file)

    g.launch()

    g.part_disk("/dev/sda","msdos")
    g.part_set_mbr_id("/dev/sda",1,0x83)
    g.mkfs("ext2", "/dev/sda1")
    g.part_set_bootable("/dev/sda", 1, 1)
    g.sync()
    
    #g.shutdown()


def generate_boot_content(url, dest_dir, distro, create_volume):
    """
    Insert kernel, ramdisk and syslinux.cfg file in dest_dir
    source from url
    """
    # TODO: Add support for something other than rhel5

    if distro == "rpm":
        kernel_url = url + "images/pxeboot/vmlinuz"
        initrd_url = url + "images/pxeboot/initrd.img"
        if create_volume:
            # NOTE: RHEL5 and other older Anaconda versions do not support specifying the CDROM device - use with caution
            cmdline = "ks=http://169.254.169.254/latest/user-data repo=cdrom:/dev/vdb"
        else:
            cmdline = "ks=http://169.254.169.254/latest/user-data"
    elif distro == "ubuntu":
        kernel_url = url + "main/installer-amd64/current/images/netboot/ubuntu-installer/amd64/linux"
        initrd_url = url + "main/installer-amd64/current/images/netboot/ubuntu-installer/amd64/initrd.gz"
        cmdline = "append preseed/url=http://169.254.169.254/latest/user-data debian-installer/locale=en_US console-setup/layoutcode=us netcfg/choose_interface=auto keyboard-configuration/layoutcode=us priority=critical --"

    kernel_dest = os.path.join(dest_dir,"vmlinuz")
    http_download_file(kernel_url, kernel_dest)

    initrd_dest = os.path.join(dest_dir,"initrd.img")
    http_download_file(initrd_url, initrd_dest)

    pvgrub_conf="""# This file is for use with pv-grub; legacy grub is not installed in this image
default=0
timeout=0
#hiddenmenu
title Anaconda install inside of EC2
        root (hd0,0)
        kernel /boot/grub/vmlinuz ks=http://169.254.169.254/latest/user-data
        initrd /boot/grub/initrd.img
"""

    f = open(os.path.join(dest_dir, "menu.lst"),"w")
    f.write(pvgrub_conf)
    f.close()

def http_download_file(url, filename):
    fd = os.open(filename,os.O_CREAT | os.O_WRONLY | os.O_TRUNC)
    try:
        ozutil.http_download_file(url, fd, False, logging.getLogger())
    finally:
        os.close(fd)


def copy_content_to_image(contentdir, target_image):
    g = guestfs.GuestFS()
    g.add_drive(target_image)
    g.launch()
    g.mount_options ("", "/dev/sda1", "/")
    g.mkdir_p("/boot/grub")
    for filename in os.listdir(contentdir):
        g.upload(os.path.join(contentdir,filename),"/boot/grub/" + filename)
    g.sync()
    #g.shutdown()


def install_extract_bits(install_file, distro):
    if distro == "rpm":
        return ks_extract_bits(install_file)
    elif distro == "ubuntu":
        return preseed_extract_bits(install_file)
    else:
        return (None, None, None, None)

def preseed_extract_bits(preseedfile):

    install_url = None
    console_password = None
    console_command = None
    poweroff = False

    for line in preseedfile.splitlines():

        # Network console lines look like this:
        # d-i network-console/password password r00tme
        m = re.match("d-i\s+network-console/password\s+password\s+(\S+)", line)
        if m and len(m.groups()) == 1:
            console_password = m.group(1)
            console_command = "ssh installer@%s\nNote that you MUST connect to this session for the install to continue\nPlease do so now\n"
            continue

        # Preseeds do not need to contain any explicit pointers to network install sources
        # Users can specify the install-url on the cmd line or provide a hint in a
        # comment line that looks like this:
        # "#ubuntu_baseurl=http://us.archive.ubuntu.com/ubuntu/dists/precise/"
        m = re.match("#ubuntu_baseurl=(\S+)", line)
        if m and len(m.groups()) == 1:
            install_url = m.group(1)

        # A preseed poweroff directive looks like this:
        # d-i debian-installer/exit/poweroff boolean true
        if re.match("d-i\s+debian-installer/exit/poweroff\s+boolean\s+true", line):
            poweroff=True
            continue

    return (install_url, console_password, console_command, poweroff)


def ks_extract_bits(ksfile):
    # I briefly looked at pykickstart but it more or less requires you know the version of the
    # format you wish to use 
    # The approach below actually works as far back as RHEL5 and as recently as F18

    install_url = None
    console_password = None
    console_command = None
    poweroff = False
    distro = None

    for line in ksfile.splitlines():
        # Install URL lines look like this
        # url --url=http://download.devel.redhat.com/released/RHEL-5-Server/U9/x86_64/os/
        m = re.match("url.*--url=(\S+)", line)
        if m and len(m.groups()) == 1:
            install_url = m.group(1)
            continue

        # VNC console lines look like this
        # Inisist on a password being set
        # vnc --password=vncpasswd    
        m = re.match("vnc.*--password=(\S+)", line)
        if m and len(m.groups()) == 1:
            console_password = m.group(1)
            console_command = "vncviewer %s:1"
            continue

        # SSH console lines look like this
        # Inisist on a password being set
        # ssh --password=sshpasswd    
        m = re.match("ssh.*--password=(\S+)", line)
        if m and len(m.groups()) == 1:
            console_password = m.group(1)
            console_command = "ssh root@%s"
            continue

        # We require a poweroff after install to detect completion - look for the line
        if re.match("poweroff", line):
            poweroff=True
            continue

    return (install_url, console_password, console_command, poweroff)


def do_pw_sub(ks_file, admin_password):
    f = open(ks_file, "r")
    working_ks = ""
    for line in f:
        working_ks += Template(line).safe_substitute({ 'adminpw': admin_password })
    f.close()
    return working_ks

def detect_distro(install_script):

    for line in install_script.splitlines():
        if re.match("d-i\s+debian-installer", line):
            return "ubuntu"
        elif re.match("%packages", line):
            return "rpm"

    return None


def generate_install_image(ks_file, root_pw, image_filename):
    working_kickstart = do_pw_sub(ks_file, root_pw)
    distro = detect_distro(working_kickstart)
    if not detect_distro:
        raise Exception("Could not determine distro type from install script '%s'" % (ks_file))
    (install_tree_url, console_password, console_command, poweroff) = install_extract_bits(working_kickstart, distro)

    if not poweroff:
        if distro == "rpm":
            raise Exception("ERROR: supplied kickstart file must contain a 'poweroff' line")
        elif distro == "ubuntu":
            raise Exception("ERROR: supplied preseed must contain a 'd-i debian-installer/exit/poweroff boolean true' line")

    if not install_tree_url:
        raise Exception("ERROR: no install tree URL specified and could not extract one from the kickstart/install-script")

    create_ext2_image(image_filename, image_size=(1024*1024*200))
    tmp_content_dir = mkdtemp()
    try:
        generate_boot_content(install_tree_url, tmp_content_dir, distro, False)
        copy_content_to_image(tmp_content_dir, image_filename)
    finally:
        shutil.rmtree(tmp_content_dir)

if __name__ == "__main__":
    # stuff only to run when not called via 'import' here
    if len(sys.argv) != 4:
        print
        print "Create a pvgrub bootable image for EC2"
        print 
        print "usage: %s <ks_file> <root_pw> <image_file>" % sys.argv[0]
        print
        sys.exit(1)

    generate_install_image(sys.argv[1], sys.argv[2], sys.argv[3])
