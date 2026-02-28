class Dictare < Formula
  desc "Voice-to-text for your terminal"
  homepage "https://github.com/dragfly/dictare"
  url "https://github.com/dragfly/dictare.git", tag: "v3.0.0a61"
  license "MIT"

  depends_on "portaudio"
  depends_on "uv"

  def install
    # Determine extras based on architecture
    if Hardware::CPU.arm?
      pkg_spec = "dictare[mlx]"
    else
      pkg_spec = "dictare"
    end

    system "uv", "tool", "install",
           "--python", "3.11",
           "--prerelease=allow",
           pkg_spec

    # Create a wrapper script so brew can manage the binary
    uv_tool_bin = Pathname.new(Dir.home) / ".local" / "bin" / "dictare"
    bin.install_symlink uv_tool_bin => "dictare" if uv_tool_bin.exist?
  end

  def post_install
    system "#{bin}/dictare", "service", "install"
  rescue => e
    opoo "Could not auto-start dictare service: #{e}"
  end

  def caveats
    <<~EOS
      dictare requires Accessibility permission for keyboard simulation.

        1. Open System Settings -> Privacy & Security -> Accessibility
        2. Click '+' and add your terminal app
        3. Enable the toggle
        4. Restart your terminal

      If you installed on Apple Silicon, the MLX backend is included
      for on-device speech recognition.
    EOS
  end

  test do
    assert_match version.to_s, shell_output("#{bin}/dictare --version")
  end
end
