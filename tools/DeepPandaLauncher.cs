using System;
using System.Diagnostics;
using System.IO;
using System.Text;
using System.Windows.Forms;

internal static class DeepPandaLauncher
{
    private const int MaxCapturedOutput = 12000;

    [STAThread]
    private static int Main()
    {
        string root = FindProjectRoot(AppDomain.CurrentDomain.BaseDirectory);
        if (root == null)
        {
            MessageBox.Show(
                "DeepPanda depo klasoru bulunamadi. DeepPanda.exe dosyasini depo icindeki dist klasorunde tutun.",
                "DeepPanda",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            return 2;
        }

        string script = Path.Combine(root, "run-desktop.ps1");
        string powershell = Path.Combine(
            Environment.GetFolderPath(Environment.SpecialFolder.System),
            @"WindowsPowerShell\v1.0\powershell.exe");
        if (!File.Exists(powershell))
        {
            MessageBox.Show(
                "Windows PowerShell bulunamadi; Qt uygulamasi baslatilamadi.",
                "DeepPanda",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            return 3;
        }

        var startInfo = new ProcessStartInfo
        {
            FileName = powershell,
            Arguments = "-NoLogo -NoProfile -File \"" + script + "\"",
            WorkingDirectory = root,
            UseShellExecute = false,
            CreateNoWindow = true,
            RedirectStandardOutput = true,
            RedirectStandardError = true
        };

        try
        {
            using (var process = new Process { StartInfo = startInfo })
            {
                var output = new StringBuilder();
                process.OutputDataReceived += delegate(object sender, DataReceivedEventArgs args)
                {
                    AppendBounded(output, args.Data);
                };
                process.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs args)
                {
                    AppendBounded(output, args.Data);
                };
                process.Start();
                process.BeginOutputReadLine();
                process.BeginErrorReadLine();
                process.WaitForExit();
                process.WaitForExit();

                if (process.ExitCode != 0)
                {
                    string detail = output.ToString().Trim();
                    if (detail.Length > 3000)
                        detail = detail.Substring(detail.Length - 3000);
                    MessageBox.Show(
                        "Qt uygulamasi baslatilamadi (cikis kodu " + process.ExitCode + ")."
                            + (detail.Length == 0 ? "" : Environment.NewLine + Environment.NewLine + detail),
                        "DeepPanda",
                        MessageBoxButtons.OK,
                        MessageBoxIcon.Error);
                }
                return process.ExitCode;
            }
        }
        catch (Exception error)
        {
            MessageBox.Show(
                "Qt uygulamasi baslatilamadi: " + error.Message,
                "DeepPanda",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            return 4;
        }
    }

    private static string FindProjectRoot(string start)
    {
        var directory = new DirectoryInfo(start);
        while (directory != null)
        {
            if (File.Exists(Path.Combine(directory.FullName, "run-desktop.ps1"))
                && Directory.Exists(Path.Combine(directory.FullName, "desktop"))
                && Directory.Exists(Path.Combine(directory.FullName, "backend")))
                return directory.FullName;
            directory = directory.Parent;
        }
        return null;
    }

    private static void AppendBounded(StringBuilder output, string line)
    {
        if (String.IsNullOrEmpty(line))
            return;
        lock (output)
        {
            output.AppendLine(line);
            if (output.Length > MaxCapturedOutput)
                output.Remove(0, output.Length - MaxCapturedOutput);
        }
    }
}
