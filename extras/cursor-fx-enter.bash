# cursor-fx-enter.bash - cursor-fx's Enter and done moments for bash, in Ghostty.
# Installed by extras/install.sh with the cursor-fx step (its own line in ~/.bashrc).
#
# cursor-fx shaders can't see keys: `cursor-fx signal` tells them Enter was pressed, and
# `cursor-fx signal done` that a long command ended. cursor-fx ships the zsh hook only; this is the
# bash one (Omarchy's default shell). Enter fires as a command starts (PS0, so an empty Enter sends
# nothing); done fires at the next prompt when the command ran longer than AFTERBURN_CFX_DONE_SECS
# (default 5). Both run detached, print nothing and leave $? alone.
#
# It follows no theme: it only tells cursor-fx what happened, and the effect you picked plays.
# `cursor-fx enter off` mutes it (cursor-fx checks that itself). Done needs bash 5.3+ (Omarchy's);
# older bash gets Enter only.

if [[ $- == *i* && -n ${GHOSTTY_RESOURCES_DIR-} && -z ${__AFB_CFX_HOOKED-} ]] \
   && command -v cursor-fx >/dev/null 2>&1; then
  __AFB_CFX_HOOKED=1
  __AFB_CFX_TTY=$(tty 2>/dev/null) || __AFB_CFX_TTY=""
  [[ $__AFB_CFX_TTY == /dev/* ]] || __AFB_CFX_TTY=""
  __AFB_CFX_T0=""

  # From PS0. In a ${ ...; } it runs in this shell (bash 5.3+), so the start time is kept for done.
  __afb_cfx_enter() {
    __AFB_CFX_T0=${EPOCHREALTIME-}
    [[ -n $__AFB_CFX_TTY ]] || return 0
    # A detached subshell: no job-table entry, so no "[1] 1234" or "Done" lines.
    ( cursor-fx signal --tty "$__AFB_CFX_TTY" </dev/null >/dev/null 2>&1 & )
  }

  # From PROMPT_COMMAND, last, so the fail flash (first) still sees $?. Returns $? unchanged.
  __afb_cfx_done() {
    local rc=$? t0=$__AFB_CFX_T0 now
    __AFB_CFX_T0=""
    if [[ -n $t0 && -n $__AFB_CFX_TTY && -n ${EPOCHREALTIME-} ]]; then
      now=${EPOCHREALTIME/[.,]/} t0=${t0/[.,]/}   # microseconds (always 6 decimals)
      if (( 10#$now - 10#$t0 > ${AFTERBURN_CFX_DONE_SECS:-5} * 1000000 )); then
        ( cursor-fx signal "done" --tty "$__AFB_CFX_TTY" </dev/null >/dev/null 2>&1 & )
      fi
    fi
    return "$rc"
  }

  if (( BASH_VERSINFO[0] > 5 || (BASH_VERSINFO[0] == 5 && BASH_VERSINFO[1] >= 3) )); then
    PS0="${PS0-}"'${ __afb_cfx_enter; }'
  else
    PS0="${PS0-}"'$(__afb_cfx_enter)'
  fi

  # PROMPT_COMMAND may be an array (bash 5.1+) or a string: both are handled.
  # shellcheck disable=SC2178,SC2128
  __afb_cfx_register() {
    local - e
    set +u
    if [[ ${PROMPT_COMMAND@a} == *a* ]]; then
      for e in ${PROMPT_COMMAND[@]+"${PROMPT_COMMAND[@]}"}; do
        [[ $e == __afb_cfx_done* ]] && return 0
      done
      PROMPT_COMMAND+=(__afb_cfx_done)
    else
      # PROMPT_COMMAND is a plain string here (bash before 5.1, or set as one).
      case ${PROMPT_COMMAND-} in *__afb_cfx_done*) return 0 ;; esac
      PROMPT_COMMAND="${PROMPT_COMMAND:+$PROMPT_COMMAND; }__afb_cfx_done"
    fi
  }
  __afb_cfx_register
fi
