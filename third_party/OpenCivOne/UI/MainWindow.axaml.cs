using Avalonia.Controls;
using OpenCivOne.Localization;
using Project1991.Classic.Avalonia;

namespace OpenCivOne.UI;

public partial class MainWindow : Window
{
	private bool closing;

	public MainWindow()
	{
		InitializeComponent();
		Title = ClassicProductIdentity.WindowTitle;

		Thread.CurrentThread.Name ??= "OpenCivOne main thread";

		this.classicGameView.ShowRuntimeFailureOverlay = false;
		this.classicGameView.RuntimeFinished += HandleRuntimeFinished;
		Closing += HandleClosing;
	}

	private void HandleRuntimeFinished(object? sender, EventArgs e)
	{
		Exception? failure = this.classicGameView.Surface.Failure;
		if (failure is ResourceMissingException)
		{
			MessageBox.Show(
				this,
				failure.Message,
				ClassicShellText.ResourceErrorTitle,
				MessageBoxIcon.Error,
				MessageBoxButtons.OK);
		}
		else if (failure is not null)
		{
			string logFilePath =
				this.classicGameView.Surface.RuntimeOptions.GetLogFilePath(
					"Exception.log");
			bool logWritten = WriteExceptionLog(failure, logFilePath);
			string errorText = logWritten
				? $"{ClassicShellText.EngineError}\n\n" +
					$"{ClassicShellText.ExceptionLogLocation}\n{logFilePath}"
				: ClassicShellText.EngineError;

			MessageBox.Show(
				this,
				errorText,
				ClassicShellText.EngineErrorTitle,
				MessageBoxIcon.Error,
				MessageBoxButtons.OK);
		}

		this.closing = true;
		Close();
	}

	private void HandleClosing(object? sender, WindowClosingEventArgs e)
	{
		if (this.closing)
		{
			return;
		}

		if (MessageBox.Show(
			this,
			ClassicShellText.ExitQuestion,
			ClassicShellText.ExitTitle,
			MessageBoxIcon.Question,
			MessageBoxButtons.OKCancel,
			MessageBoxDefaultButton.Button2) == MessageBoxResult.OK)
		{
			this.closing = true;
			this.classicGameView.RequestStop();
			return;
		}

		e.Cancel = true;
	}

	private bool WriteExceptionLog(
		Exception exception,
		string logFilePath)
	{
		try
		{
			using StreamWriter writer =
				new(logFilePath, true);
			writer.WriteLine("---------------------------");
			writer.WriteLine(
				$"Timestamp: {DateTimeOffset.Now:O}");
			writer.WriteLine(
				$"Version: {ClassicProductIdentity.Version}");
			writer.WriteLine(
				$"Exception type: {exception.GetType().FullName}");
			writer.WriteLine($"Message: {exception.Message}");
			writer.WriteLine($"Source: {exception.Source}");
			writer.WriteLine($"Stack trace: {exception.StackTrace}");
			return true;
		}
		catch (Exception logFailure)
		{
			MessageBox.Show(
				this,
				$"{ClassicShellText.ExceptionLogError}{logFailure.Message}",
				ClassicShellText.EngineErrorTitle,
				MessageBoxIcon.Error,
				MessageBoxButtons.OK);
			return false;
		}
	}
}
