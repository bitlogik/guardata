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
  cd "$(dirname "$2")"
  LINK=$(readlink "$(basename "$2")")
  while [ "$LINK" ]; do
    cd "$(dirname "$LINK")"
    LINK=$(readlink "$(basename "$2")")
  done
  REALPATH="$PWD/$(basename "$2")"
  cd "$OURPWD"
  echo "$REALPATH"
}

if [[ "$(uname)" == "Darwin" ]]
then
  realpath='realpathOSX'
else
  realpath='realpath'
fi

# Cross-shell script directory detection
if [ -n "$BASH_SOURCE" ]; then
  script_dir=$(dirname $($realpath -s "$BASH_SOURCE"))
elif [ -n "$ZSH_VERSION" ]; then
  script_dir=$(dirname $($realpath -s $0))
fi

# Run python script and source
if [[ "$(uname)" == "Darwin" ]]
then
  source_file=$TMPDIR/guardata-temp-$(uuidgen)
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
