#!/bin/bash
###################################
#
# installboot.sh
#
# An installer for pycftboot
# and all dependencies
#
# Author: T. Olson
#
# Last modified: 2/29/16
#
###################################

echo  `date`

## Set up environment (make sure INSTALLPATH matches here and in bootconfig)
## Also, bootconfig must be readable from INSTALLPATH

INSTALLPATH=$HOME

source $INSTALLPATH/bootconfig

mkdir $INSTALLPATH/bootstrap-install/
cd $INSTALLPATH/bootstrap-install/


## Install gmp with --enable-cxx option

# download
echo "Downloading gmp..."
FILE=download-gmp.tar.bz2
if [ ! -f $FILE ]
then
    wget -O $FILE https://gmplib.org/download/gmp/gmp-6.1.0.tar.bz2
fi

# unpack
echo "Unpacking..."
tar -xjf $FILE
cd gmp-6.1.0/

# compile
echo "Configuring and installing gmp to $INSTALLPATH/ -- see gmp.log for output"
./configure --prefix=$INSTALLPATH --enable-cxx > $INSTALLPATH/gmp.log
make -j8 >> $INSTALLPATH/gmp.log
make check >> $INSTALLPATH/gmp.log
make install >> $INSTALLPATH/gmp.log
cd ..
echo "gmp finished."


## Install sdpb 

# download
echo "Downloading sdpb..."
git clone https://github.com/davidsd/sdpb 
cd sdpb

# update makefile
# escape special chars for sed
ESCAPEDPATH=$(printf '%s' "$INSTALLPATH" | sed 's/[#\/]/\\\0/g')
ESCAPEDBOOST=$(printf '%s' "$BOOST_ROOT" | sed 's/[#\/]/\\\0/g')

# update gmp paths
sed -i.bak 's/GMP.*=.*$/GMPINCLUDEDIR = '$ESCAPEDPATH'\/include\nGMPLIBDIR = '$ESCAPEDPATH'\/lib/' Makefile
sed -i.bak 's/\(-L$[{]LIBDIR[}]\)/\0 -L${GMPLIBDIR}/' Makefile

# update boost paths
sed -i.bak 's/BOOST.*=.*$/BOOSTINCLUDEDIR = '$ESCAPEDBOOST'\/include/' Makefile
sed -i.bak 's/LIBDIR.*=.*$/LIBDIR = '$ESCAPEDBOOST'\/lib/' Makefile

# compile
echo "Compiling sdpb -- see sdpb.log for output"
make -j8 >> $INSTALLPATH/sdpb.log

# install
echo "Copying sdpb to $INSTALLPATH/bin"
if [ ! -d $INSTALLPATH/bin ]
then
    mkdir $INSTALLPATH/bin
fi
cp -f ./sdpb $INSTALLPATH/bin

cd ..
echo "sdpb finished."


## Install symengine

# download
echo "Downloading symengine and symengine.py..."
git clone https://github.com/symengine/symengine
git clone https://github.com/symengine/symengine.py
cd symengine

# load correct version
git checkout `cat ../symengine.py/symengine_version.txt`

# compile symengine
echo "Compiling symengine -- see sym.log for output"
mkdir build 
cd build
# WITH_PTHREAD and WITH_SYMENGINE_THREAD_SAFE might be helpful as well
CC=gcc cmake -DCMAKE_INSTALL_PREFIX:PATH="$INSTALLPATH"\
    -DCMAKE_PREFIX_PATH=$MPFR_ROOT\
    -DWITH_MPFR:BOOL=ON \
    -DWITH_SYMENGINE_THREAD_SAFE:BOOL=ON \
    .. > $INSTALLPATH/sym.log
make -j8 >> $INSTALLPATH/sym.log
cd ../../symengine.py

# set up symengine.py
echo "Installing symengine.py -- see sym.log for output"
#python setup.py install --prefix=$INSTALLPATH build --symengine-dir=$INSTALLPATH/bootstrap-install/symengine/build --compiler=gcc
CC=gcc python setup.py install --user build --symengine-dir=$INSTALLPATH/bootstrap-install/symengine/build --compiler=gcc >> $INSTALLPATH/sym.log

cd ..
echo "symengine finished."


## Install mpmath

# download
echo "Downloading mpmath..."
FILE=download-mpmath.tgz
wget -O $FILE https://pypi.python.org/packages/source/m/mpmath/mpmath-0.19.tar.gz

# unpack
echo "Unpacking..."
tar -xzf $FILE
cd mpmath-0.19/

# install
echo "Installing mpmath -- see mp.log for output"
python setup.py install --user > $INSTALLPATH/mp.log


cd ..
echo "mpmath done."


## Install sympy

# download 
echo "Downloading sympy..."
git clone git://github.com/sympy/sympy.git
cd sympy/

# install
echo "Installing sympy -- see sympy.log for output"
python setup.py install --user > $INSTALLPATH/sympy.log

cd ..
echo "sympy done."


## Install pycftboot

# download
echo "Downloading pycftboot..."
git clone https://github.com/cbehan/pycftboot/
cd pycftboot

# update file
echo "Updating paths and packages."
sed -i.bak 's/^import os/import subprocess/' bootstrap.py
sed -i.bak 's/^\(\s*\)os\.spawnvp(os\.P_WAIT, "\/usr\/bin\/sdpb", \(.*\))$/\1with open(name + ".log", "a+") as log_file:\n\1    subprocess.Popen(\2, stdout=log_file).wait()\n\1log_file.close()/' bootstrap.py

echo "pycftboot done."

echo -e "\nInstall finished.\\n\n\
bootstrap.py is available in:
$INSTALLPATH/bootstrap-install/pycftboot/\n\
Don't forget to run\n\
  > source /path/to/bootconfig\n\
when you log on. You can add that line to ~/.bashrc to automate it.\n\
Happy bootstrapping!"

echo  `date`
