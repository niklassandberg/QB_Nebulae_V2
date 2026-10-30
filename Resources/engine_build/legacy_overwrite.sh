# Leftovers of the old way: before the engines' plugins were packages, they
# were built and copied in by hand (the old Resources/rpi4_image/build_sc.sh,
# build_pd_libs.sh, removed 2026-10-25, in the git history). Their files are
# on such a Nebulae without belonging to a
# package, and pacman refuses to install a package over them ("... exists in
# filesystem"; sc3-plugins failed like that on 2026-10-25). These folders may
# be overwritten by the packages.
#
# Read by build_engines.sh (next to this file) and Code/scripts/engines_check.sh.
# Once no Nebulae has hand-installed plugins any more (every one updated with
# the packages), comment the lines out: then a real conflict stops the install.
LEGACY_OVERWRITE=(
    --overwrite '/usr/share/SuperCollider/Extensions/*'   # build_sc.sh: classes, UGens
    --overwrite '/usr/lib/SuperCollider/plugins/*'        # build_sc.sh: sc3-plugins .so
    --overwrite '/usr/lib/pd/extra/*'                     # build_pd_libs.sh: ELSE, cyclone
)
