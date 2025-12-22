# Dire Wolf IQ

### Overview

I decided to build a complete APRS RX-TX with a good demodulator and packet decoder and a WEB interface to monitor RX performances.


## New Features vs original Direwolf

- **IQ Input with FM Demodulation.**
  
    Direct IQ input from SDR sources (rx_sdr, csdr, etc.) with built-in FM demodulation. Eliminates need for external FM demodulation tools. See [IQ_INPUT.md](IQ_INPUT.md) for details.

- **Web Interface with Live Charts.**
  
    A lightweight Flask-based web UI provides real-time RSSI/SNR charts and station statistics. Chart tooltips show Callsign, Via (Direct or last digipeater), and timestamp when hovering points. See `scripts/web_interface.py` and `scripts/templates/index.html`.

- **SoapySDR IQ Pipeline Helper Scripts.**
  
    Helper Python scripts in `scripts/` (notably `soapysdr_to_direwolf.py`) provide a unified SoapySDR → `csdr` → Dire Wolf IQ pipeline with an optional web-based monitor. See `scripts/README.md` and `scripts/SOAPYSDR_TO_DIREWOLF.md`.

## Documentation

[Stable Version](https://github.com/wb2osz/direwolf/tree/master/doc)

[Latest Development Version ("dev" branch)](https://github.com/wb2osz/direwolf/tree/dev/doc)

[Additional Topics](https://github.com/wb2osz/direwolf-doc)

[Power Point presentations](https://github.com/wb2osz/direwolf-presentation)  -- Why not give a talk at a local club meeting?

Youtube has many interesting and helpful videos.  Searching for [direwolf tnc](https://www.youtube.com/results?search_query=direwolf+tnc) or [direwolf aprs](https://www.youtube.com/results?search_query=direwolf+aprs)  will produce the most relevant results. 

**All APRS users should read this:**   [Understanding APRS Packets]( https://github.com/wb2osz/aprsspec/raw/main/Understanding-APRS-Packets.pdf)

## Installation

### Windows

Go to the [**releases** page](https://github.com/wb2osz/direwolf/releases).   Download a zip file with "win" in its name, unzip it, and run direwolf.exe from a command window.

You can also build it yourself from source.  For more details see the **User Guide** in the [**doc** directory](https://github.com/wb2osz/direwolf/tree/master/doc).

### Linux - Using git clone (recommended)

***Note that this has changed for version 1.6.  There are now a couple extra steps.***

First you will need to install some software development packages using different commands depending on your flavor of Linux.
In most cases, the first few  will already be there and the package installer will tell you that installation is not necessary.

On Debian / Ubuntu / Raspbian / Raspberry Pi OS:

    sudo apt-get install git
    sudo apt-get install gcc
    sudo apt-get install g++
    sudo apt-get install make
    sudo apt-get install cmake
    sudo apt-get install libasound2-dev
    sudo apt-get install libudev-dev
    sudo apt-get install libavahi-client-dev
    # This is only needed to use the GPIO pins for PTT:
    sudo apt-get install libgpiod-dev

Or on Red Hat / Fedora / CentOS:

    sudo yum install git
    sudo yum install gcc
    sudo yum install gcc-c++
    sudo yum install make
    sudo yum install alsa-lib-devel
    sudo yum install libudev-devel
    sudo yum install avahi-devel

CentOS 6 & 7 currently have cmake 2.8 but we need 3.1 or later.
First you need to enable the EPEL repository.  Add a symlink if you don't already have the older version and want to type cmake rather than cmake3.

    sudo yum install epel-release
    sudo rpm -e cmake
    sudo yum install cmake3
    sudo ln -s /usr/bin/cmake3 /usr/bin/cmake

Then on any flavor of Linux:

    cd ~
    git clone https://www.github.com/wb2osz/direwolf
    cd direwolf
    git checkout dev
    mkdir build && cd build
    cmake ..
    make -j4
    sudo make install
    make install-conf

This gives you the latest development version.  Leave out the "git checkout dev" to get the most recent stable release.

For more details see the **User Guide** in the [**doc** directory](https://github.com/wb2osz/direwolf/tree/master/doc).  Special considerations for the Raspberry Pi are found in **Raspberry-Pi-APRS.pdf**

### Linux - Using apt-get (Debian flavor operating systems)

Results will vary depending on your hardware platform and operating system version because it depends on various volunteers who perform the packaging. Expect the version to lag significantly behind development.

    sudo apt-get update
    apt-cache showpkg direwolf
    sudo apt-get install direwolf

### Linux - Using yum (Red Hat flavor operating systems)

Results will vary depending on your hardware platform and operating system version because it depends on various volunteers who perform the packaging.  Expect the version to lag significantly behind development.

    sudo yum check-update
    sudo yum list direwolf
    sudo yum install direwolf

### Macintosh macOS - Using Homebrew

The following instructions have been verified on macOS Ventura 13.6 (M2) and macOS High Sierra 10.13.6 (Intel).

First make sure that you have the following tools installed on your Mac:

- [Xcode or Xcode Command Line Tools](https://developer.apple.com/xcode/resources/)
- [Homebrew](https://brew.sh/)

You will need to install the following packages using Homebrew:

    brew install cmake
    brew install portaudio
    brew install hidapi

Then follow the same instructions as above for the Linux `git clone` build:

    cd ~
    git clone https://www.github.com/wb2osz/direwolf
    cd direwolf
    git checkout dev
    mkdir build && cd build
    cmake ..
    make -j4
    sudo make install
    make install-conf

This gives you the latest development version.  Leave out the "git checkout dev" to get the most recent stable release.

For more information, see the ***User Guide*** in the [**doc** directory](https://github.com/wb2osz/direwolf/tree/master/doc).

If you have problems,  post them to the [Dire Wolf packet TNC](https://groups.io/g/direwolf) discussion group.

### Macintosh macOS - Prebuilt version

You can also install a pre-built version from MacPorts.  Keeping this up to date depends on volunteers who perform the packaging. This version could lag behind development.

    sudo port install direwolf

## Join the conversation

Here are some good places to ask questions and share your experience:

- [Dire Wolf Software TNC](https://groups.io/g/direwolf) 

- [Raspberry Pi 4 Ham Radio](https://groups.io/g/RaspberryPi-4-HamRadio)

- [linuxham](https://groups.io/g/linuxham)

- [TAPR aprssig](http://www.tapr.org/pipermail/aprssig/)

The github "issues" section is for reporting software defects and enhancement requests.  It is NOT a place to ask questions or have general discussions.  Please use one of the locations above.

[![Star History Chart](https://api.star-history.com/svg?repos=wb2osz/direwolf&type=Date)](https://star-history.com/#wb2osz/direwolf&Date)
