# supercft

Repository for superconformal bootstrap in 2<d<4.

## Install on U-M Flux cluster

The folder `installboot/` contains two files:
```
bootconfig
installboot.sh
```

0. If you do not want it to install to your `$HOME` directory, edit the `$INSTALLPATH` in both files (make sure they agree).
1. Load all modules and set paths by executing `source bootconfig`
2. Copy `bootconfig` to the folder specified by `$INSTALLPATH` (default `$HOME`).
3. Run the installer `installboot.sh`
4. Add `source /path/to/bootconfig` to your `~/.bashrc` file to automatically set up the environment
