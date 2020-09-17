#!/usr/bin/env bash
: '
Create a temporary environment and initialize a test setup for guardata.

Run `tests/scripts/run_testenv.sh --help` for more information.
'

# Make sure this script is sourced
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]
then
echo "This script must be sourced. Use --help for more information."
exit 1
fi

realpathOSX() {
  OURPWD=$PWD
  cd "$(dirname "$1")"
  LINK=$(readlink "$(basename "$1")")
  while [ "$LINK" ]; do
    cd "$(dirname "$LINK")"
    LINK=$(readlink "$(basename "$1")")
  done
  REALPATH="$PWD/$(basename "$1")"
  cd "$OURPWD"
  echo "$REALPATH"
}

if [ "$(uname)" == "Darwin" ]
then
  script_dir=$(dirname $(realpathOSX $BASH_SOURCE))
else
  # Cross-shell script directory detection
  if [ -n "$BASH_SOURCE" ]; then
    script_dir=$(dirname $(realpath -s $BASH_SOURCE))
  elif [ -n "$ZSH_VERSION" ]; then
    script_dir=$(dirname $(realpath -s $0))
  fi
fi

# Run python script and source
if [ "$(uname)" == "Darwin" ]
then
  source_file=$TMPDIR/guardata-temp
  if [ -f $source_file ]; then
    rm -f $source_file
  fi
  touch $TMPDIR/guardata-temp
else
  source_file=$(tempfile)
fi
$script_dir/run_testenv.py --source-file $source_file $@ || return $?
source $source_file

# Clean up
rm $source_file
unset source_file
unset script_dir
