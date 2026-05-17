class Dictare < Formula
  desc "Voice-first control for AI coding agents"
  homepage "https://github.com/dragfly/dictare"
  url "file://PLACEHOLDER"
  sha256 "PLACEHOLDER"
  license "MIT"
  preserve_rpath

  depends_on "portaudio"
  depends_on "uv"

  def install
    dictare_tarball = "PLACEHOLDER_DICTARE"
    extras = Hardware::CPU.arm? ? "[mlx]" : ""

    ENV["UV_TOOL_DIR"] = (libexec/"uv-tools").to_s
    ENV["UV_TOOL_BIN_DIR"] = (libexec/"bin").to_s
    ENV["UV_PYTHON_INSTALL_DIR"] = (libexec/"uv-python").to_s

    system "uv", "tool", "install",
           "--python", "3.11",
           "--prerelease=allow",
           "#{dictare_tarball}#{extras}"

    dylib_dir = libexec/"uv-tools/dictare/lib/python3.11/site-packages/av/.dylibs"
    if dylib_dir.exist?
      dylib_dir.glob("*.dylib").each do |dylib|
        system "install_name_tool", "-id", "@rpath/#{dylib.basename}", dylib
      end
    end

    bin.install_symlink (libexec/"bin/dictare") => "dictare"
  end

  def post_install
    real_home = ENV["HOME"] || Pathname.new("~").expand_path.to_s
    dictare_dir = Pathname.new(real_home)/".dictare"
    dictare_dir.mkpath
    python_path = dictare_dir/"python_path"
    begin
      File.write python_path, "#{opt_libexec}/uv-tools/dictare/bin/python"
    rescue Errno::EACCES, Errno::EPERM => e
      opoo "Could not update #{python_path}: #{e.message}. Run `dictare service install` or `dictare service start` to repair it."
    end
  end

  def caveats
    <<~EOS
      On first launch, macOS will ask for Input Monitoring permission.
      A system dialog will appear — click "Open System Settings" and
      enable the toggle for Dictare. That's it.

      If you installed on Apple Silicon, the MLX backend is included
      for hardware-accelerated on-device speech recognition.
    EOS
  end

  test do
    assert_match "PLACEHOLDER", shell_output("#{bin}/dictare --version")
  end
end
