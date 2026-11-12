using System;
using System.Diagnostics;
using System.IO;
using System.IO.Compression;
using System.Reflection;
using System.Text;
using System.Threading;
using System.Windows.Forms;

internal static class DeepPandaSetup
{
    [STAThread]
    private static int Main(string[] args)
    {
        Application.EnableVisualStyles();
        Application.SetCompatibleTextRenderingDefault(false);

        string tempRoot = Path.Combine(Path.GetTempPath(), "DeepPandaSetup-" + Guid.NewGuid().ToString("N"));
        try
        {
            Directory.CreateDirectory(tempRoot);
            ExtractResource("DeepPandaPayload.zip", Path.Combine(tempRoot, "DeepPandaPayload.zip"));
            ExtractResource("DeepPandaPayload.sha256", Path.Combine(tempRoot, "DeepPandaPayload.sha256"));
            string installer = Path.Combine(tempRoot, "Install-DeepPanda.ps1");
            ExtractResource("Install-DeepPanda.ps1", installer);

            string powershell = Path.Combine(
                Environment.GetFolderPath(Environment.SpecialFolder.System),
                @"WindowsPowerShell\v1.0\powershell.exe");
            if (!File.Exists(powershell))
                throw new FileNotFoundException("Windows PowerShell was not found.", powershell);

            bool quiet = Array.Exists(args, delegate(string argument)
            {
                return String.Equals(argument, "/quiet", StringComparison.OrdinalIgnoreCase)
                    || String.Equals(argument, "/q", StringComparison.OrdinalIgnoreCase);
            });
            var startInfo = new ProcessStartInfo
            {
                FileName = powershell,
                Arguments = "-NoLogo -NoProfile -File " + Quote(installer)
                    + " -PackageRoot " + Quote(tempRoot) + (quiet ? " -Quiet" : ""),
                WorkingDirectory = tempRoot,
                UseShellExecute = false,
                CreateNoWindow = false,
                WindowStyle = ProcessWindowStyle.Normal
            };
            StringBuilder output = new StringBuilder();
            if (quiet)
            {
                startInfo.RedirectStandardOutput = true;
                startInfo.RedirectStandardError = true;
            }
            using (var process = Process.Start(startInfo))
            {
                if (process == null)
                    throw new InvalidOperationException("The setup script process could not be started.");
                if (quiet)
                {
                    process.OutputDataReceived += delegate(object sender, DataReceivedEventArgs eventArgs)
                    {
                        AppendBounded(output, eventArgs.Data);
                    };
                    process.ErrorDataReceived += delegate(object sender, DataReceivedEventArgs eventArgs)
                    {
                        AppendBounded(output, eventArgs.Data);
                    };
                    process.BeginOutputReadLine();
                    process.BeginErrorReadLine();
                }
                process.WaitForExit();
                if (quiet)
                    process.WaitForExit();
                if (process.ExitCode != 0 && quiet)
                    throw new InvalidOperationException(
                        "Installer process exited with code " + process.ExitCode + ".\r\n\r\n" + output);
                return process.ExitCode;
            }
        }
        catch (Exception error)
        {
            MessageBox.Show(
                "DeepPanda kurulumu baslatilamadi.\r\n\r\n" + error.Message,
                "DeepPanda Kurulumu",
                MessageBoxButtons.OK,
                MessageBoxIcon.Error);
            return 1;
        }
        finally
        {
            try
            {
                if (Directory.Exists(tempRoot))
                    Directory.Delete(tempRoot, true);
            }
            catch (Exception cleanupError)
            {
                MessageBox.Show(
                    "Kurulum gecici dosyalari temizlenemedi: " + cleanupError.Message,
                    "DeepPanda Kurulumu",
                    MessageBoxButtons.OK,
                    MessageBoxIcon.Warning);
            }
        }
    }

    private static void ExtractResource(string name, string destination)
    {
        string resourceName = "DeepPandaSetup." + name;
        using (Stream input = Assembly.GetExecutingAssembly().GetManifestResourceStream(resourceName))
        {
            if (input == null)
                throw new FileNotFoundException("Setup resource is missing: " + name);
            using (var output = new FileStream(destination, FileMode.CreateNew, FileAccess.Write, FileShare.None))
                input.CopyTo(output);
        }
    }

    private static string Quote(string value)
    {
        return "\"" + value.Replace("\"", "\\\"") + "\"";
    }

    private static void AppendBounded(StringBuilder output, string line)
    {
        if (String.IsNullOrEmpty(line))
            return;
        lock (output)
        {
            output.AppendLine(line);
            if (output.Length > 8000)
                output.Remove(0, output.Length - 8000);
        }
    }
}
