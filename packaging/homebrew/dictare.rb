class Dictare < Formula
  desc "Voice-first control for AI coding agents"
  homepage "https://github.com/dragfly/dictare"
  url "PLACEHOLDER_PYPI_URL"
  sha256 "PLACEHOLDER_PYPI_SHA256"
  license "MIT"

  DICTARE_BOOTSTRAP_VERSION = "PLACEHOLDER_VERSION"
  DICTARE_BOOTSTRAP_URL = "PLACEHOLDER_PYPI_URL"
  DICTARE_BOOTSTRAP_SHA256 = "PLACEHOLDER_PYPI_SHA256"

  depends_on "portaudio"
  depends_on "uv"
  depends_on :macos

  resource "launcher" do
    url "https://github.com/dragfly/dictare/releases/download/launcher/Dictare-launcher-universal.zip"
    sha256 "PLACEHOLDER_LAUNCHER_SHA256"
  end

  def install
    (libexec/"bin").mkpath
    (libexec/"bin/dictare").write <<~BASH
      #!/usr/bin/env bash
      set -euo pipefail

      DICTARE_BOOTSTRAP_VERSION="#{DICTARE_BOOTSTRAP_VERSION}"
      DICTARE_BOOTSTRAP_URL="#{DICTARE_BOOTSTRAP_URL}"
      DICTARE_BOOTSTRAP_SHA256="#{DICTARE_BOOTSTRAP_SHA256}"
      DICTARE_HOMEBREW_BUNDLE="#{opt_libexec}/bundle/Dictare.app"
      DICTARE_HOMEBREW_BIN="#{opt_bin}"
      DICTARE_UV="#{Formula["uv"].opt_bin}/uv"
      DICTARE_RUNTIME_ROOT="${DICTARE_RUNTIME_ROOT:-$HOME/.local/share/dictare}"
      export DICTARE_HOMEBREW_BUNDLE
      export PATH="$DICTARE_HOMEBREW_BIN:$PATH"

      current_cli="$DICTARE_RUNTIME_ROOT/current/bin/dictare"

      record_homebrew_bundle() {
        mkdir -p "$HOME/.dictare"
        printf '%s\\n' "$DICTARE_HOMEBREW_BUNDLE" > "$HOME/.dictare/homebrew_bundle_path"
      }

      show_setup_hint() {
        cat <<EOF
      Dictare is installed through Homebrew.

      Finish setup:
        dictare setup

      Homebrew manages the entry point, macOS dependencies, and the signed launcher source.
      Dictare manages the runtime:
        dictare upgrade
        dictare rollback
        dictare repair
      EOF
      }

      write_shim() {
        local shim="$HOME/.local/bin/dictare"
        local trash="$HOME/.dictare/trash"
        mkdir -p "$HOME/.local/bin" "$trash"
        if [[ -e "$shim" || -L "$shim" ]]; then
          if grep -q 'current/bin/dictare' "$shim" 2>/dev/null; then
            chmod +x "$shim"
            return
          fi
          local backup="$trash/dictare.$(date +%s)"
          local i=0
          while [[ -e "$backup" || -L "$backup" ]]; do
            i=$((i + 1))
            backup="$trash/dictare.$(date +%s).$i"
          done
          mv "$shim" "$backup"
        fi
        cat > "$shim" <<'EOF'
      #!/usr/bin/env bash
      set -euo pipefail
      exec "$HOME/.local/share/dictare/current/bin/dictare" "$@"
      EOF
        chmod +x "$shim"
      }

      bootstrap_runtime() {
        if [[ ! -x "$DICTARE_UV" ]]; then
          DICTARE_UV="$(command -v uv || true)"
        fi
        if [[ -z "$DICTARE_UV" || ! -x "$DICTARE_UV" ]]; then
          echo "uv is required but was not found. Run: brew install uv" >&2
          exit 1
        fi

        local version="$DICTARE_BOOTSTRAP_VERSION"
        local runtime="$DICTARE_RUNTIME_ROOT/versions/$version"
        local current="$DICTARE_RUNTIME_ROOT/current"
        local previous="$DICTARE_RUNTIME_ROOT/previous"
        local extras=""
        local spec=""

        mkdir -p "$DICTARE_RUNTIME_ROOT/versions" "$DICTARE_RUNTIME_ROOT/locks"

        if [[ ! -x "$runtime/bin/python" ]]; then
          echo "Creating Dictare runtime: $runtime"
          "$DICTARE_UV" venv --python 3.11 "$runtime"
        fi

        if [[ "$(uname -s)" == "Darwin" && "$(uname -m)" == "arm64" ]]; then
          extras="mlx"
        fi

        if [[ -n "$extras" ]]; then
          spec="dictare[$extras] @ ${DICTARE_BOOTSTRAP_URL}#sha256=${DICTARE_BOOTSTRAP_SHA256}"
        else
          spec="dictare @ ${DICTARE_BOOTSTRAP_URL}#sha256=${DICTARE_BOOTSTRAP_SHA256}"
        fi

        echo "Installing Dictare runtime $version"
        "$DICTARE_UV" pip install --python "$runtime/bin/python" --prerelease=allow "$spec"
        "$runtime/bin/dictare" --version | grep -q "$version"

        "$runtime/bin/python" - "$current" "$previous" "$runtime" <<'PY'
      import os
      import sys
      from pathlib import Path

      current = Path(sys.argv[1])
      previous = Path(sys.argv[2])
      runtime = Path(sys.argv[3])
      old = current.resolve() if current.exists() else None

      if old and old != runtime:
          prev_tmp = previous.with_name(f".{previous.name}.tmp.{os.getpid()}")
          if prev_tmp.exists() or prev_tmp.is_symlink():
              prev_tmp.unlink()
          prev_tmp.symlink_to(old, target_is_directory=True)
          os.replace(prev_tmp, previous)

      tmp = current.with_name(f".{current.name}.tmp.{os.getpid()}")
      if tmp.exists() or tmp.is_symlink():
          tmp.unlink()
      tmp.symlink_to(runtime, target_is_directory=True)
      os.replace(tmp, current)
      PY

        write_shim
      }

      record_homebrew_bundle

      case "${1:-}" in
        --homebrew-entrypoint-version)
          echo "dictare Homebrew entry point #{DICTARE_BOOTSTRAP_VERSION}"
          exit 0
          ;;
      esac

      if [[ -x "$current_cli" ]]; then
        exec "$current_cli" "$@"
      fi

      case "${1:-}" in
        setup|repair|upgrade)
          bootstrap_runtime
          exec "$current_cli" "$@"
          ;;
        *)
          show_setup_hint
          exit 1
          ;;
      esac
    BASH
    chmod 0755, libexec/"bin/dictare"

    bin.install_symlink (libexec/"bin/dictare") => "dictare"

    resource("launcher").stage do
      bundle_dir = libexec/"bundle"
      if Pathname("Dictare.app").directory?
        bundle_dir.install "Dictare.app"
      elsif Pathname("Contents").directory?
        app = bundle_dir/"Dictare.app"
        app.mkpath
        app.install "Contents"
      else
        odie "Launcher archive did not contain Dictare.app"
      end
    end
  end

  def caveats
    <<~EOS
      Finish setup:

        dictare setup

      Homebrew manages the Dictare entry point, macOS dependencies, and the
      signed launcher source. Dictare manages its runtime:

        dictare upgrade
        dictare rollback
        dictare repair

      For a clean reinstall:

        dictare uninstall
        brew uninstall dictare
        brew install dictare
        dictare setup
    EOS
  end

  test do
    assert_match "dictare Homebrew entry point #{DICTARE_BOOTSTRAP_VERSION}",
                 shell_output("#{bin}/dictare --homebrew-entrypoint-version")
  end
end
