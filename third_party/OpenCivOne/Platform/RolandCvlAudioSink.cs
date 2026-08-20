using System.Diagnostics;
using System.Runtime.InteropServices;
using OpenCivOne.Runtime;

namespace OpenCivOne.Platform;

/// <summary>
/// Plays the original Civilization Roland driver streams through the Windows
/// MIDI mapper. The proprietary sequence bytes are read from the owner's
/// RSOUND.CVL at runtime and are never copied into Project1991.
/// </summary>
public sealed class RolandCvlAudioSink : IClassicAudioSink
{
	private static readonly TimeSpan CloseTimeout =
		TimeSpan.FromSeconds(2);
	private readonly object synchronization = new();
	private readonly LinkedList<AudioCommand> commands = new();
	private readonly AutoResetEvent commandAvailable = new(false);
	private readonly ClassicRuntimeOptions options;
	private readonly WindowsMidiOutput midiOutput;
	private readonly CivWinWaveCatalog waveCatalog;
	private readonly WindowsWaveAudioPlayer wavePlayer;
	private RolandCvlSequencer? sequencer;
	private Thread? workerThread;
	private TaskCompletionSource<Exception?>? closeCompletion;
	private Exception? workerFailure;
	private string? startupAudioDiagnostic;
	private int commandAvailableDisposed;
	private bool deviceMayBeOpen;
	private bool midiEnabled;
	private bool waveEnabled;
	private bool initialized;
	private bool closing;
	private bool closed;

	public RolandCvlAudioSink(ClassicRuntimeOptions options)
		: this(
			options,
			new WindowsMidiOutput(),
			new CivWinWaveCatalog(options?.CivWinPath),
			new WindowsWaveAudioPlayer())
	{
	}

	internal RolandCvlAudioSink(
		ClassicRuntimeOptions options,
		WindowsMidiOutput midiOutput)
		: this(
			options,
			midiOutput,
			new CivWinWaveCatalog(null),
			new WindowsWaveAudioPlayer())
	{
	}

	internal RolandCvlAudioSink(
		ClassicRuntimeOptions options,
		WindowsMidiOutput midiOutput,
		CivWinWaveCatalog waveCatalog,
		WindowsWaveAudioPlayer wavePlayer)
	{
		this.options =
			options ?? throw new ArgumentNullException(nameof(options));
		this.midiOutput =
			midiOutput ?? throw new ArgumentNullException(nameof(midiOutput));
		this.waveCatalog =
			waveCatalog ?? throw new ArgumentNullException(nameof(waveCatalog));
		this.wavePlayer =
			wavePlayer ?? throw new ArgumentNullException(nameof(wavePlayer));
	}

	public bool IsAvailable
	{
		get
		{
			lock (this.synchronization)
			{
				if (this.closed ||
					this.closing ||
					this.workerFailure is not null)
				{
					return false;
				}

				bool midiAvailable =
					this.midiOutput.IsAvailable &&
					File.Exists(
						this.options.GetResourceFilePath("RSOUND.CVL"));
				bool waveAvailable =
					this.waveCatalog.IsConfigured &&
					this.wavePlayer.IsAvailable;
				return midiAvailable || waveAvailable;
			}
		}
	}

	public void Initialize()
	{
		lock (this.synchronization)
		{
			if (this.initialized)
			{
				return;
			}

			if (this.closed ||
				this.closing ||
				this.workerFailure is not null ||
				Volatile.Read(
					ref this.commandAvailableDisposed) != 0)
			{
				throw new ObjectDisposedException(nameof(RolandCvlAudioSink));
			}

			Exception? midiFailure = null;
			Exception? waveFailure = null;
			this.midiEnabled = false;
			this.waveEnabled = false;
			this.startupAudioDiagnostic = null;

			if (this.midiOutput.IsAvailable &&
				File.Exists(
					this.options.GetResourceFilePath("RSOUND.CVL")))
			{
				try
				{
					string path =
						this.options.GetResourceFilePath("RSOUND.CVL");
					byte[] driverBytes = File.ReadAllBytes(path);
					this.sequencer =
						new RolandCvlSequencer(
							driverBytes,
							this.midiOutput);
					this.midiOutput.Open();
					this.deviceMayBeOpen = true;
					this.midiEnabled = true;
				}
				catch (Exception exception)
				{
					midiFailure = exception;
					this.sequencer = null;
					this.midiEnabled = false;
				}
			}

			if (this.waveCatalog.IsConfigured)
			{
				try
				{
					if (!this.wavePlayer.IsAvailable)
					{
						throw new PlatformNotSupportedException(
							"WinMM waveform playback is unavailable.");
					}

					// File validation and native initialization are performed
					// by the actor after it starts. Initialize must never wait
					// for OneDrive-backed owner data on the game thread.
					this.waveEnabled = true;
				}
				catch (Exception exception)
				{
					waveFailure = exception;
					this.waveEnabled = false;
				}
			}

			if (!this.midiEnabled && !this.waveEnabled)
			{
				Exception unavailableFailure =
					CombineFailures(
						"Classic MIDI and CivWin WAV initialization both failed.",
						midiFailure,
						waveFailure) ??
					new InvalidOperationException(
						"No configured Classic audio backend is available.");
				throw unavailableFailure;
			}

			Exception? optionalFailure =
				this.midiEnabled ? waveFailure : midiFailure;
			if (optionalFailure is not null)
			{
				this.startupAudioDiagnostic =
					$"Optional Classic audio backend initialization failed " +
					$"({optionalFailure.GetType().Name}): " +
					optionalFailure.Message;
			}

			try
			{
				this.workerFailure = null;
				this.initialized = true;
				this.workerThread = new Thread(this.RunWorker)
				{
					IsBackground = true,
					Name = "Project1991 Classic audio",
					// The original 60-Hz score clock is audible. Keep it ahead
					// of ordinary build/UI worker contention so sustained CPU
					// load does not flatten the authored tempo.
					Priority = ThreadPriority.AboveNormal,
				};
				this.workerThread.Start();
			}
			catch (Exception startFailure)
			{
				this.initialized = false;
				this.sequencer = null;
				Exception? midiCloseFailure = null;
				Exception? waveCloseFailure = null;
				try
				{
					if (this.deviceMayBeOpen)
					{
						this.midiOutput.Dispose();
					}
					this.deviceMayBeOpen = false;
				}
				catch (Exception closeFailure)
				{
					midiCloseFailure = closeFailure;
				}

				try
				{
					if (this.waveEnabled)
					{
						this.wavePlayer.Close();
					}
					this.waveEnabled = false;
				}
				catch (Exception closeFailure)
				{
					waveCloseFailure = closeFailure;
				}

				Exception? cleanupFailure =
					CombineFailures(
						"Classic MIDI and CivWin WAV startup cleanup failed.",
						midiCloseFailure,
						waveCloseFailure);
				if (cleanupFailure is not null)
				{
					throw new AggregateException(
						"Classic audio worker start and cleanup failed.",
						startFailure,
						cleanupFailure);
				}

				throw;
			}
		}
	}

	public void PlayTune(short tune, ushort parameter)
	{
		lock (this.synchronization)
		{
			this.ThrowIfWorkerFailed();
			this.EnsureInitialized();
			this.Enqueue(
				new AudioCommand(
					AudioCommandType.Play,
					tune,
					parameter));
		}
	}

	public void AdvanceTick()
	{
		lock (this.synchronization)
		{
			this.ThrowIfWorkerFailed();
		}
	}

	public void Stop()
	{
		lock (this.synchronization)
		{
			this.ThrowIfWorkerFailed();
			if (this.initialized && this.workerFailure is null)
			{
				this.commands.Clear();
				this.commands.AddFirst(
					new AudioCommand(AudioCommandType.Stop));
				this.commandAvailable.Set();
			}
		}
	}

	public void Close()
	{
		TaskCompletionSource<Exception?>? completion = null;
		lock (this.synchronization)
		{
			if (this.closed)
			{
				return;
			}
			this.closing = true;

			if (this.closeCompletion is not null)
			{
				completion = this.closeCompletion;
			}
			else if (this.initialized &&
				this.workerThread?.IsAlive == true)
			{
				this.initialized = false;
				this.commands.Clear();
				completion =
					new TaskCompletionSource<Exception?>(
						TaskCreationOptions.RunContinuationsAsynchronously);
				this.closeCompletion = completion;
				this.commands.AddFirst(
					new AudioCommand(
						AudioCommandType.Close,
						Completion: completion));
				this.commandAvailable.Set();
			}
			else if (this.deviceMayBeOpen || this.waveEnabled)
			{
				completion =
					new TaskCompletionSource<Exception?>(
						TaskCreationOptions.RunContinuationsAsynchronously);
				this.closeCompletion = completion;
				Thread retryThread =
					new(() => this.RunDirectClose(completion))
					{
						IsBackground = true,
						Name = "Project1991 Classic audio close",
					};
				retryThread.Start();
			}
		}

		if (completion is not null)
		{
			if (!completion.Task.Wait(CloseTimeout))
			{
				throw new TimeoutException(
					"Classic audio close did not complete within " +
					$"{CloseTimeout.TotalSeconds:0.#} seconds.");
			}

			Exception? failure =
				completion.Task.GetAwaiter().GetResult();
			if (failure is not null)
			{
				throw failure;
			}

			return;
		}

		Exception? waveDirectFailure = null;
		Exception? midiDirectFailure = null;
		try
		{
			if (this.waveEnabled)
			{
				this.wavePlayer.Close();
				this.waveEnabled = false;
			}
		}
		catch (Exception exception)
		{
			waveDirectFailure = exception;
		}

		try
		{
			if (this.deviceMayBeOpen)
			{
				this.midiOutput.Dispose();
			}
		}
		catch (Exception exception)
		{
			midiDirectFailure = exception;
		}

		lock (this.synchronization)
		{
			this.deviceMayBeOpen = this.midiOutput.IsOpen;
			this.midiEnabled = false;
			if (!this.deviceMayBeOpen && !this.waveEnabled)
			{
				this.closed = true;
			}
		}

		this.DisposeCommandSignal();
		Exception? directFailure =
			CombineFailures(
				"Classic CivWin WAV and MIDI direct close both failed.",
				waveDirectFailure,
				midiDirectFailure);
		if (directFailure is not null)
		{
			throw directFailure;
		}
	}

	private void RunDirectClose(
		TaskCompletionSource<Exception?> completion)
	{
		Exception? waveFailure = null;
		Exception? midiFailure = null;
		try
		{
			if (this.waveEnabled)
			{
				this.wavePlayer.Close();
				this.waveEnabled = false;
			}
		}
		catch (Exception exception)
		{
			waveFailure = exception;
		}

		try
		{
			if (this.deviceMayBeOpen)
			{
				this.midiOutput.Dispose();
			}
		}
		catch (Exception exception)
		{
			midiFailure = exception;
		}

		lock (this.synchronization)
		{
			this.closeCompletion = null;
			this.deviceMayBeOpen = this.midiOutput.IsOpen;
			this.midiEnabled = false;
			if (!this.deviceMayBeOpen && !this.waveEnabled)
			{
				this.closed = true;
			}
		}

		this.DisposeCommandSignal();
		Exception? failure =
			CombineFailures(
				"Classic CivWin WAV and MIDI retry close both failed.",
				waveFailure,
				midiFailure);
		completion.TrySetResult(failure);
	}

	private void RunWorker()
	{
		try
		{
			using WindowsTimerResolution timerResolution =
				WindowsTimerResolution.TryRequest();
			this.InitializeWaveFromWorker();
			if (this.startupAudioDiagnostic is not null)
			{
				this.ReportAudioDiagnostic(
					this.startupAudioDiagnostic);
				this.startupAudioDiagnostic = null;
			}

			this.sequencer?.Reset();
			OriginalAudioTickClock clock =
				new(
					Stopwatch.Frequency,
					Stopwatch.GetTimestamp());
			while (true)
			{
				while (this.TryDequeue(out AudioCommand command))
				{
					switch (command.Type)
					{
						case AudioCommandType.Play:
							this.PlayFromWorker(
								command.Tune,
								command.Parameter);
							break;

						case AudioCommandType.Stop:
							this.StopFromWorker();
							break;

						case AudioCommandType.Close:
							Exception? closeFailure =
								this.CloseFromWorker();
							this.CompleteClose(
								command.Completion!,
								closeFailure);
							return;

						default:
							throw new InvalidOperationException(
								"Unknown Classic audio command.");
					}
				}

				long now = Stopwatch.GetTimestamp();
				if (clock.IsTickDue(now))
				{
					this.sequencer?.AdvanceTick();
					clock.CompleteTick(Stopwatch.GetTimestamp());
					continue;
				}

				this.commandAvailable.WaitOne(
					clock.GetWaitMilliseconds(now));
			}
		}
		catch (Exception exception)
		{
			this.HandleWorkerFailure(exception);
		}
	}

	private void InitializeWaveFromWorker()
	{
		if (!this.waveEnabled)
		{
			return;
		}

		if (!this.waveCatalog.TryValidateRequiredFiles(
			out string validationFailure))
		{
			this.waveEnabled = false;
			this.ReportAudioDiagnostic(
				$"CivWin WAV preflight failed: {validationFailure}");
			if (!this.midiEnabled)
			{
				throw new InvalidDataException(
					$"CivWin WAV preflight failed: {validationFailure}");
			}

			return;
		}

		try
		{
			this.wavePlayer.Initialize();
		}
		catch (Exception exception)
		{
			this.waveEnabled = false;
			this.ReportAudioDiagnostic(
				$"CivWin WAV initialization failed " +
				$"({exception.GetType().Name}): {exception.Message}");
			if (!this.midiEnabled)
			{
				throw new InvalidOperationException(
					"CivWin WAV initialization failed.",
					exception);
			}
		}
	}

	private void PlayFromWorker(short tune, ushort parameter)
	{
		if (this.waveEnabled &&
			this.waveCatalog.TryResolve(tune, out string wavePath))
		{
			// Both operations are performed by this single actor. MIDI is
			// therefore silent before the replacing WAV is started.
			this.sequencer?.Stop();
			if (this.wavePlayer.TryPlayFile(wavePath))
			{
				return;
			}

			string failure =
				this.wavePlayer.LastFailure ??
				"Unknown CivWin WAV playback failure.";
			this.ReportAudioDiagnostic(
				$"CivWin WAV tune {tune} fell back to RSOUND: " +
				failure);
			if (this.sequencer is null)
			{
				throw new InvalidOperationException(failure);
			}
		}
		else if (this.waveEnabled &&
			!this.wavePlayer.TryStop())
		{
			this.ReportAudioDiagnostic(
				this.wavePlayer.LastFailure ??
				"Unknown CivWin WAV stop failure.");
		}

		this.sequencer?.PlayTune(tune, parameter);
	}

	private void StopFromWorker()
	{
		if (this.waveEnabled && !this.wavePlayer.TryStop())
		{
			this.ReportAudioDiagnostic(
				this.wavePlayer.LastFailure ??
					"Unknown CivWin WAV stop failure.");
		}

		this.sequencer?.Stop();
	}

	private void ReportAudioDiagnostic(string diagnostic)
	{
		try
		{
			File.AppendAllText(
				this.options.GetLogFilePath("Audio.log"),
				$"[{DateTimeOffset.Now:O}] {diagnostic}" +
					Environment.NewLine);
		}
		catch (Exception)
		{
			// Diagnostics are best effort and are already off the game thread.
		}
	}

	private void EnsureInitialized()
	{
		if (!this.initialized)
		{
			throw new InvalidOperationException(
				"The Classic Roland audio sink is not initialized.");
		}
	}

	private void ThrowIfWorkerFailed()
	{
		if (this.workerFailure is not null)
		{
			throw new InvalidOperationException(
				"The Classic audio worker failed.",
				this.workerFailure);
		}
	}

	private void Enqueue(AudioCommand command)
	{
		this.commands.AddLast(command);
		this.commandAvailable.Set();
	}

	private bool TryDequeue(out AudioCommand command)
	{
		lock (this.synchronization)
		{
			if (this.commands.Count == 0)
			{
				command = default;
				return false;
			}

			command = this.commands.First!.Value;
			this.commands.RemoveFirst();
			return true;
		}
	}

	private Exception? CloseFromWorker()
	{
		Exception? waveCloseFailure = null;
		Exception? stopFailure = null;
		Exception? closeFailure = null;
		try
		{
			if (this.waveEnabled)
			{
				this.wavePlayer.Close();
				this.waveEnabled = false;
			}
		}
		catch (Exception exception)
		{
			waveCloseFailure = exception;
		}

		try
		{
			this.sequencer?.Stop();
		}
		catch (Exception exception)
		{
			stopFailure = exception;
		}

		try
		{
			if (this.deviceMayBeOpen)
			{
				this.midiOutput.Dispose();
			}
		}
		catch (Exception exception)
		{
			closeFailure = exception;
		}

		return CombineFailures(
			"Classic MIDI/WAV shutdown reported multiple failures.",
			CombineFailures(
				"Classic CivWin WAV close and MIDI stop both failed.",
				waveCloseFailure,
				stopFailure),
			closeFailure);
	}

	private void CompleteClose(
		TaskCompletionSource<Exception?> completion,
		Exception? failure)
	{
		lock (this.synchronization)
		{
			this.initialized = false;
			this.commands.Clear();
			this.closeCompletion = null;
			this.workerFailure = failure;
			this.deviceMayBeOpen = this.midiOutput.IsOpen;
			this.midiEnabled = false;
			if (!this.deviceMayBeOpen && !this.waveEnabled)
			{
				this.closed = true;
			}
		}

		this.DisposeCommandSignal();
		completion.TrySetResult(failure);
	}

	private void HandleWorkerFailure(Exception primaryFailure)
	{
		TaskCompletionSource<Exception?>? completion;
		lock (this.synchronization)
		{
			this.initialized = false;
			this.commands.Clear();
			this.workerFailure = primaryFailure;
			this.closing = true;
			completion = this.closeCompletion;
			this.closeCompletion = null;
		}

		this.DisposeCommandSignal();
		completion?.TrySetResult(primaryFailure);

		Exception? waveCloseFailure = null;
		Exception? stopFailure = null;
		Exception? closeFailure = null;
		try
		{
			if (this.waveEnabled)
			{
				this.wavePlayer.Close();
				this.waveEnabled = false;
			}
		}
		catch (Exception exception)
		{
			waveCloseFailure = exception;
		}

		try
		{
			this.sequencer?.Stop();
		}
		catch (Exception exception)
		{
			stopFailure = exception;
		}

		try
		{
			if (this.deviceMayBeOpen)
			{
				this.midiOutput.Dispose();
			}
		}
		catch (Exception exception)
		{
			closeFailure = exception;
		}

		Exception failure = primaryFailure;
		Exception? cleanupFailure =
			CombineFailures(
				"Classic MIDI/WAV emergency cleanup reported multiple failures.",
				CombineFailures(
					"Classic CivWin WAV close and MIDI emergency stop both failed.",
					waveCloseFailure,
					stopFailure),
				closeFailure);
		if (cleanupFailure is not null)
		{
			failure = new AggregateException(
				"Classic audio worker and cleanup failed.",
				primaryFailure,
				cleanupFailure);
		}

		lock (this.synchronization)
		{
			this.workerFailure = failure;
			this.deviceMayBeOpen = this.midiOutput.IsOpen;
			this.midiEnabled = false;
			if (!this.deviceMayBeOpen && !this.waveEnabled)
			{
				this.closed = true;
			}
		}
	}

	private void DisposeCommandSignal()
	{
		if (Interlocked.Exchange(
			ref this.commandAvailableDisposed,
			1) == 0)
		{
			this.commandAvailable.Dispose();
		}
	}

	private static Exception? CombineFailures(
		string aggregateMessage,
		Exception? first,
		Exception? second)
	{
		if (first is not null && second is not null)
		{
			return new AggregateException(
				aggregateMessage,
				first,
				second);
		}

		return first ?? second;
	}

	private enum AudioCommandType
	{
		Play,
		Stop,
		Close,
	}

	private readonly record struct AudioCommand(
		AudioCommandType Type,
		short Tune = 0,
		ushort Parameter = 0,
		TaskCompletionSource<Exception?>? Completion = null);

	private sealed class WindowsTimerResolution : IDisposable
	{
		private const uint MillisecondPeriod = 1;
		private bool active;

		private WindowsTimerResolution(bool active)
		{
			this.active = active;
		}

		public static WindowsTimerResolution TryRequest()
		{
			if (!OperatingSystem.IsWindows())
			{
				return new WindowsTimerResolution(false);
			}

			try
			{
				return new WindowsTimerResolution(
					TimeBeginPeriod(MillisecondPeriod) == 0);
			}
			catch (Exception)
			{
				// Precision remains protected by the bounded catch-up clock
				// when the host cannot grant a finer Windows timer period.
				return new WindowsTimerResolution(false);
			}
		}

		public void Dispose()
		{
			if (!this.active)
			{
				return;
			}
			this.active = false;

			try
			{
				TimeEndPeriod(MillisecondPeriod);
			}
			catch (Exception)
			{
				// Restoring the advisory timer period must never turn an
				// otherwise clean audio shutdown into a gameplay failure.
			}
		}

		[DllImport("winmm.dll", EntryPoint = "timeBeginPeriod")]
		private static extern uint TimeBeginPeriod(uint period);

		[DllImport("winmm.dll", EntryPoint = "timeEndPeriod")]
		private static extern uint TimeEndPeriod(uint period);
	}
}

/// <summary>
/// Maintains the original PIT-derived Roland worker cadence without tying
/// score progress to the presentation timer.
/// </summary>
internal sealed class OriginalAudioTickClock
{
	private const int MaximumImmediateCatchUpTicks = 1;
	private const double MaximumCatchUpIntervals = 2d;
	private readonly double frequency;
	private readonly double tickInterval;
	private double nextTick;
	private int immediateCatchUpTicks;

	public OriginalAudioTickClock(long frequency, long startTimestamp)
	{
		if (frequency <= 0)
		{
			throw new ArgumentOutOfRangeException(
				nameof(frequency),
				frequency,
				"Clock frequency must be positive.");
		}

		this.frequency = frequency;
		this.tickInterval = this.frequency / Hertz;
		this.nextTick = startTimestamp + this.tickInterval;
	}

	public const double Hertz = 1_193_180d / 0x4dae;

	internal double TickInterval => this.tickInterval;

	public bool IsTickDue(long timestamp)
	{
		return timestamp >= this.nextTick;
	}

	public int GetWaitMilliseconds(long timestamp)
	{
		if (this.IsTickDue(timestamp))
		{
			return 0;
		}

		return Math.Max(
			1,
			(int)Math.Ceiling(
				(this.nextTick - timestamp) *
				1000d /
				this.frequency));
	}

	public void CompleteTick(long timestamp)
	{
		this.nextTick += this.tickInterval;
		if (this.nextTick > timestamp)
		{
			this.immediateCatchUpTicks = 0;
			return;
		}

		double lateness = timestamp - this.nextTick;
		if (lateness >=
				this.tickInterval * MaximumCatchUpIntervals ||
			this.immediateCatchUpTicks >= MaximumImmediateCatchUpTicks)
		{
			// A blocked MIDI device or suspended process must not release a
			// burst of stale score events. Resume one full interval from now.
			this.nextTick = timestamp + this.tickInterval;
			this.immediateCatchUpTicks = 0;
			return;
		}

		// A single coarse Windows wake-up can cross two adjacent deadlines.
		// Permit one immediate recovery tick so that rare scheduler jitter
		// does not permanently slow the score, but never busy-spin a backlog.
		this.immediateCatchUpTicks++;
	}
}

/// <summary>
/// Bounds-checked reconstruction of the event worker inside the original
/// RSOUND.CVL. It emits MIDI messages but contains no copied score data.
/// </summary>
internal sealed class RolandCvlSequencer
{
	private const int ExportTableOffset = 0x30;
	private const int ExpectedExportCount = 11;
	private const int TuneCount = 45;
	private const int TrackCount = 8;
	private const int MaximumEventsPerTrackTick = 1024;
	private const int MidiVolumeController = 7;
	private const int MidiPanController = 10;
	private const int MidiResetAllControllers = 121;
	private const int MidiAllNotesOff = 123;

	private static readonly IReadOnlyDictionary<int, int> SetupHelperTracks =
		new Dictionary<int, int>
		{
			[0x048b] = 0,
			[0x0481] = 1,
			[0x0477] = 2,
			[0x046d] = 3,
			[0x0463] = 4,
			[0x0459] = 5,
			[0x044f] = 6,
			[0x0445] = 7,
		};

	private static readonly HashSet<int> ParameterizedTuneNumbers =
		[
			5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18,
		];

	private static readonly HashSet<int> DirectSetupTuneNumbers =
		[
			3, 4,
			19, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32,
			34, 36, 37, 40, 41, 42, 43,
		];

	private readonly byte[] module;
	private readonly WindowsMidiOutput output;
	private readonly int dataBase;
	private readonly int[] tuneFunctions;
	private readonly TrackState[] tracks;
	private bool tune35Alternate;
	private ushort randomState;

	public RolandCvlSequencer(
		byte[] driverFile,
		WindowsMidiOutput output)
	{
		ArgumentNullException.ThrowIfNull(driverFile);
		this.output =
			output ?? throw new ArgumentNullException(nameof(output));
		this.module = ExtractModule(driverFile);

		int exportCount = ReadUInt16(this.module, ExportTableOffset);
		if (exportCount != ExpectedExportCount)
		{
			throw new InvalidDataException(
				$"RSOUND.CVL exports {exportCount} functions; " +
				$"{ExpectedExportCount} were expected.");
		}

		int playFunction =
			ReadUInt16(this.module, ExportTableOffset + 2 + 2);
		(this.dataBase, int tuneTable) =
			ReadDispatcherLayout(this.module, playFunction);
		EnsureRange(this.module, tuneTable, TuneCount * 2);

		this.tuneFunctions = new int[TuneCount];
		for (int tune = 0; tune < TuneCount; tune++)
		{
			this.tuneFunctions[tune] =
				ReadUInt16(this.module, tuneTable + (tune * 2));
		}

		this.tracks = Enumerable
			.Range(0, TrackCount)
			.Select(index =>
			{
				int eventChannel =
					index == TrackCount - 1 ? 9 : index + 1;
				int setupChannel =
					index == TrackCount - 1 ? 8 : eventChannel;
				return new TrackState(
					eventChannel,
					setupChannel);
			})
			.ToArray();
	}

	public void Reset()
	{
		foreach (TrackState track in this.tracks)
		{
			track.Deactivate();
			track.Volume = 100;
		}

		// RSOUND resets only its owned channel range, descending exactly as
		// the original driver does. Reset All Controllers is material here:
		// it also releases stale sustain before the next score begins.
		for (int channel = 9; channel >= 1; channel--)
		{
			this.output.ControlChange(
				channel,
				MidiAllNotesOff,
				0);
			this.output.ControlChange(
				channel,
				MidiResetAllControllers,
				0);
			this.output.ControlChange(
				channel,
				MidiVolumeController,
				100);
			this.output.ControlChange(
				channel,
				MidiPanController,
				64);
		}
	}

	public void Stop()
	{
		this.Reset();
	}

	public void PlayTune(short tune, ushort parameter)
	{
		if (tune is < 0 or >= TuneCount)
		{
			return;
		}

		if (tune == 0)
		{
			this.Stop();
			return;
		}
		if (tune == 1)
		{
			this.BeginOriginalStopSequence();
			return;
		}

		IReadOnlyList<TrackSetup> setup =
			this.ReadTuneSetup(tune, parameter);
		if (setup.Count == 0)
		{
			// The first vertical intentionally stays silent for the handful of
			// randomised/suspend commands not decoded yet. Never substitute an
			// invented effect for an original tune.
			return;
		}

		foreach (TrackSetup item in setup)
		{
			int absoluteStream = checked(this.dataBase + item.StreamOffset);
			EnsureRange(this.module, absoluteStream, 1);
			TrackState track = this.tracks[item.TrackIndex];
			track.Configure(item.StreamOffset);
			this.output.PitchBend(track.SetupChannel, 8192);
			this.output.ControlChange(
				track.SetupChannel,
				MidiVolumeController,
				100);
		}
	}

	private void BeginOriginalStopSequence()
	{
		const ushort stopStream = 0x2288;
		EnsureRange(
			this.module,
			checked(this.dataBase + stopStream),
			2);

		foreach (TrackState track in this.tracks)
		{
			if (!track.Active)
			{
				continue;
			}

			// This is the exact state mutation performed by RSOUND tune 1.
			// The authored 00,00 stream terminates each track at its next
			// event boundary while controller volume falls by three per tick.
			track.StreamPosition = stopStream;
			track.VolumeStep = -3;
			track.VolumeInterval = 1;
			track.VolumeIntervalCountdown = 1;
			track.NoteOffCountdown = 1;
		}
	}

	public void AdvanceTick()
	{
		this.UpdateRandomState();
		foreach (TrackState track in this.tracks)
		{
			this.AdvanceTrack(track);
		}
	}

	private void AdvanceTrack(TrackState track)
	{
		if (!track.Active)
		{
			return;
		}
		if (track.RemainingTicks == 0)
		{
			// The original driver uses the countdown byte itself as the
			// active test. A zero-duration F5 chord may finish its current
			// modulation pass, then becomes inactive at the next tick
			// instead of wrapping the byte to 255.
			track.ExpireZeroDurationChord();
			return;
		}

		if (track.NoteOffCountdown != 0)
		{
			track.NoteOffCountdown--;
			if (track.NoteOffCountdown == 0)
			{
				this.StopTrackNotes(track);
			}
		}

		track.RemainingTicks--;
		if (track.RemainingTicks == 0)
		{
			this.ReadEvents(track);
		}

		this.ApplyModulation(track);
	}

	private void ReadEvents(TrackState track)
	{
		for (int eventCount = 0;
			eventCount < MaximumEventsPerTrackTick;
			eventCount++)
		{
			byte command = this.ReadStreamByte(track, 0);
			if (command < 0x80)
			{
				byte duration = this.ReadStreamByte(track, 1);
				track.Note = command;
				track.RemainingTicks = duration;
				this.AdvanceStream(track, 2);

				if (command == 0 || duration == 0)
				{
					this.StopTrackNotes(track);
					if (duration == 0)
					{
						track.Deactivate();
					}
					return;
				}

				this.StartSingleNote(track, command);
				return;
			}

			switch (command)
			{
				case 0xf2:
					this.SkipOriginalRandomOrderCommand(track);
					break;

				case 0xf3:
					track.PanInterval =
						this.ReadStreamByte(track, 1);
					track.PanIntervalCountdown = 1;
					track.PanStep =
						unchecked((sbyte)this.ReadStreamByte(track, 2));
					this.AdvanceStream(track, 3);
					break;

				case 0xf4:
					track.Pan = this.ReadStreamByte(track, 1);
					this.output.ControlChange(
						track.Channel,
						MidiPanController,
						track.Pan);
					this.AdvanceStream(track, 2);
					break;

				case 0xf5:
					this.ReadChord(track);
					return;

				case 0xf6:
					track.Volume = this.ReadStreamByte(track, 1);
					this.output.ControlChange(
						track.Channel,
						MidiVolumeController,
						track.Volume);
					this.AdvanceStream(track, 2);
					break;

				case 0xf7:
					track.Pitch = this.ReadStreamByte(track, 1);
					this.SendPitchBend(track);
					this.AdvanceStream(track, 2);
					break;

				case 0xf8:
					track.VolumeInterval =
						this.ReadStreamByte(track, 1);
					track.VolumeIntervalCountdown =
						track.VolumeInterval;
					track.VolumeStep =
						unchecked((sbyte)this.ReadStreamByte(track, 2));
					this.AdvanceStream(track, 3);
					break;

				case 0xf9:
					track.Velocity = this.ReadStreamByte(track, 1);
					this.AdvanceStream(track, 2);
					break;

				case 0xfa:
					track.PitchInterval =
						this.ReadStreamByte(track, 1);
					track.PitchStep =
						unchecked((sbyte)this.ReadStreamByte(track, 2));
					track.PitchStepCount =
						this.ReadStreamByte(track, 3);
					track.PitchIntervalCountdown = 1;
					this.AdvanceStream(track, 4);
					break;

				case 0xfb:
					track.Gate = this.ReadStreamByte(track, 1);
					this.AdvanceStream(track, 2);
					break;

				case 0xfc:
					track.Program = this.ReadStreamByte(track, 1);
					this.output.ProgramChange(
						track.Channel,
						track.Program);
					this.AdvanceStream(track, 2);
					break;

				case 0xfd:
					track.ResetSequenceState(track.OriginalStream);
					break;

				case 0xfe:
					this.ReadNestedLoop(track);
					break;

				case 0xff:
					this.ReadLoop(track);
					break;

				default:
					throw new InvalidDataException(
						$"Unsupported RSOUND command 0x{command:x2}.");
			}
		}

		throw new InvalidDataException(
			"RSOUND stream exceeded the per-tick event safety limit.");
	}

	private void StartSingleNote(TrackState track, byte note)
	{
		track.NoteOffCountdown =
			unchecked((byte)(track.RemainingTicks - track.Gate));

		bool negativeGate = unchecked((sbyte)track.Gate) < 0;
		if (negativeGate && track.ActiveNotes[0] == note)
		{
			return;
		}

		if (!negativeGate || track.ActiveNotes[0] != note)
		{
			this.StopTrackNotes(track);
		}

		this.output.NoteOn(track.Channel, note, track.Velocity);
		track.ActiveNotes[0] = note;
	}

	private void ReadChord(TrackState track)
	{
		int noteCount = this.ReadStreamByte(track, 1);
		if (noteCount > track.ActiveNotes.Length)
		{
			throw new InvalidDataException(
				$"RSOUND chord contains {noteCount} notes; " +
				$"{track.ActiveNotes.Length} are supported by the driver.");
		}

		for (int index = 0; index < noteCount; index++)
		{
			byte note = this.ReadStreamByte(track, 2 + index);
			if (track.ActiveNotes[index] != note)
			{
				this.output.NoteOn(
					track.Channel,
					note,
					track.Velocity);
				track.ActiveNotes[index] = note;
			}
		}

		for (int index = noteCount;
			index < track.ActiveNotes.Length;
			index++)
		{
			track.ActiveNotes[index] = -1;
		}

		byte duration = this.ReadStreamByte(track, 2 + noteCount);
		track.RemainingTicks = duration;
		track.NoteOffCountdown = track.Gate == byte.MaxValue
			? unchecked((byte)(duration + 1))
			: duration < track.Gate
				? duration
				: (byte)(duration - track.Gate);
		this.AdvanceStream(track, noteCount + 3);
	}

	private void ReadLoop(TrackState track)
	{
		byte repeatCount = this.ReadStreamByte(track, 1);
		if (track.LoopRemaining == 0)
		{
			if (repeatCount == 0)
			{
				this.AdvanceStream(track, 2);
				track.LoopStart = track.StreamPosition;
				return;
			}

			track.LoopRemaining =
				unchecked((ushort)(short)(sbyte)repeatCount);
			track.StreamPosition = track.LoopStart;
			return;
		}

		track.LoopRemaining--;
		if (track.LoopRemaining != 0)
		{
			track.StreamPosition = track.LoopStart;
			return;
		}

		this.AdvanceStream(track, 2);
		track.LoopStart = track.StreamPosition;
	}

	private void ReadNestedLoop(TrackState track)
	{
		byte repeatCount = this.ReadStreamByte(track, 1);
		if (track.NestedLoopRemaining == 0)
		{
			if (repeatCount == 0)
			{
				this.AdvanceStream(track, 2);
				track.NestedLoopStart = track.StreamPosition;
				track.LoopStart = track.StreamPosition;
				track.LoopRemaining = 0;
				return;
			}

			track.NestedLoopRemaining =
				unchecked((ushort)(short)(sbyte)repeatCount);
			track.LoopStart = track.NestedLoopStart;
			track.StreamPosition = track.LoopStart;
			return;
		}

		track.NestedLoopRemaining--;
		if (track.NestedLoopRemaining != 0)
		{
			track.LoopStart = track.NestedLoopStart;
			track.StreamPosition = track.LoopStart;
			return;
		}

		this.AdvanceStream(track, 2);
		track.NestedLoopStart = track.StreamPosition;
		track.LoopStart = track.StreamPosition;
	}

	private void SkipOriginalRandomOrderCommand(TrackState track)
	{
		int itemCount = this.ReadStreamByte(track, 1);
		if (itemCount == 0)
		{
			throw new InvalidDataException(
				"RSOUND F2 contains an empty choice table.");
		}

		this.UpdateRandomState();
		int choiceIndex =
			(itemCount - 1) & (this.randomState & 0xff);
		byte choice = this.ReadStreamByte(
			track,
			checked(2 + choiceIndex));
		int targetDelta = unchecked(
			(sbyte)this.ReadStreamByte(
				track,
				checked(2 + itemCount)));
		this.AdvanceStream(track, checked(itemCount + 3));

		int target = checked(
			this.dataBase +
			track.StreamPosition +
			targetDelta);
		EnsureRange(this.module, target, 1);
		this.module[target] = choice;
	}

	private void UpdateRandomState()
	{
		this.randomState =
			RotateRight(
				unchecked((ushort)(this.randomState + 0x9249)),
				3);
	}

	private void ApplyModulation(TrackState track)
	{
		if (track.VolumeStep != 0)
		{
			track.VolumeIntervalCountdown--;
			if (track.VolumeIntervalCountdown == 0)
			{
				track.VolumeIntervalCountdown = track.VolumeInterval;
				int volume = track.Volume + track.VolumeStep;
				if (volume <= 0)
				{
					track.Volume = 0;
					track.VolumeStep = 0;
				}
				else if (volume >= 127)
				{
					track.Volume = 127;
					track.VolumeStep = 0;
				}
				else
				{
					track.Volume = (byte)volume;
				}

				this.output.ControlChange(
					track.Channel,
					MidiVolumeController,
					track.Volume);
			}
		}

		if (track.PitchStep != 0)
		{
			track.PitchIntervalCountdown--;
			if (track.PitchIntervalCountdown == 0)
			{
				track.PitchIntervalCountdown = track.PitchInterval;
				track.Pitch =
					unchecked((byte)(track.Pitch + track.PitchStep));
				this.SendPitchBend(track);
			}

			// RSOUND's FA worker decrements the duration on every normal
			// worker tick, not only on ticks where the interval expires.
			// Keeping this outside the phase gate is material: putting it
			// inside stretches authored slides by their interval and can
			// eventually generate an invalid MIDI data byte.
			track.PitchStepCount--;
			if (track.PitchStepCount == 0)
			{
				track.PitchStep = 0;
			}
		}

		if (track.PanStep != 0)
		{
			track.PanIntervalCountdown--;
			if (track.PanIntervalCountdown == 0)
			{
				track.PanIntervalCountdown = track.PanInterval;
				int pan = unchecked((byte)(track.Pan + track.PanStep));
				if (pan > 127)
				{
					pan = (pan ^ 0x7f) & 0x7f;
					track.PanIntervalCountdown = 0;
				}

				track.Pan = (byte)pan;
				this.output.ControlChange(
					track.Channel,
					MidiPanController,
					track.Pan);
			}
		}
	}

	private void StopTrackNotes(TrackState track)
	{
		for (int index = 0;
			index < track.ActiveNotes.Length;
			index++)
		{
			int note = track.ActiveNotes[index];
			if (note < 0)
			{
				break;
			}

			// The original Roland driver uses Note On with velocity zero.
			this.output.NoteOn(track.Channel, note, 0);
			track.ActiveNotes[index] = -1;
		}
	}

	private void SendPitchBend(TrackState track)
	{
		// The original UART routine writes its 8-bit state byte directly.
		// WinMM correctly requires seven-bit MIDI data. Valid owner streams
		// remain unchanged; malformed or previously over-advanced state is
		// saturated in the audible compatibility path instead of disabling
		// the whole sound engine.
		int mostSignificant = Math.Min(track.Pitch, (byte)127);
		this.output.PitchBend(
			track.Channel,
			mostSignificant << 7);
	}

	private IReadOnlyList<TrackSetup> ReadTuneSetup(
		int tune,
		ushort parameter)
	{
		int entry = this.tuneFunctions[tune];
		if (DirectSetupTuneNumbers.Contains(tune))
		{
			return this.ScanTrackSetup(entry);
		}

		if (ParameterizedTuneNumbers.Contains(tune))
		{
			int jumpTable = checked(entry - 8);
			EnsureRange(this.module, jumpTable, 8);
			int variant = parameter & 3;
			int variantEntry =
				ReadUInt16(this.module, jumpTable + (variant * 2));
			return this.ScanTrackSetup(variantEntry);
		}

		if (tune == 35)
		{
			this.tune35Alternate = !this.tune35Alternate;
			int start = this.tune35Alternate
				? checked(entry + 8)
				: ReadInt8BranchTarget(this.module, entry + 6);
			return this.ScanTrackSetup(start);
		}

		return [];
	}

	private IReadOnlyList<TrackSetup> ScanTrackSetup(int start)
	{
		EnsureRange(this.module, start, 1);
		List<TrackSetup> setup = [];
		int position = start;
		int end = Math.Min(this.module.Length, checked(start + 256));

		while (position < end)
		{
			if (this.module[position] is 0xc3 or 0xcb)
			{
				break;
			}

			if (position + 7 <= end &&
				this.module[position] == 0x8d &&
				this.module[position + 1] == 0x0e &&
				this.module[position + 4] is 0xe8 or 0xe9)
			{
				int stream = ReadUInt16(this.module, position + 2);
				int relative =
					unchecked((short)ReadUInt16(this.module, position + 5));
				int target = checked(position + 7 + relative);
				if (SetupHelperTracks.TryGetValue(
					target,
					out int trackIndex))
				{
					setup.Add(new TrackSetup(trackIndex, stream));
				}

				bool isJump = this.module[position + 4] == 0xe9;
				position += 7;
				if (isJump)
				{
					break;
				}
				continue;
			}

			position++;
		}

		return setup;
	}

	private byte ReadStreamByte(TrackState track, int relativeOffset)
	{
		int offset = checked(
			this.dataBase +
			track.StreamPosition +
			relativeOffset);
		EnsureRange(this.module, offset, 1);
		return this.module[offset];
	}

	private void AdvanceStream(TrackState track, int count)
	{
		int position = checked(track.StreamPosition + count);
		if (position > ushort.MaxValue)
		{
			throw new InvalidDataException(
				"RSOUND stream pointer overflowed its 16-bit data segment.");
		}

		track.StreamPosition = (ushort)position;
	}

	private static byte[] ExtractModule(byte[] file)
	{
		EnsureRange(file, 0, 0x1c);
		if (ReadUInt16(file, 0) != 0x5a4d)
		{
			throw new InvalidDataException(
				"RSOUND.CVL is not an MZ driver overlay.");
		}

		int bytesInLastPage = ReadUInt16(file, 2);
		int pageCount = ReadUInt16(file, 4);
		int headerLength = checked(ReadUInt16(file, 8) * 16);
		int declaredLength = checked(pageCount * 512);
		if (bytesInLastPage != 0)
		{
			declaredLength -= 512 - bytesInLastPage;
		}

		if (headerLength < 0x1c ||
			headerLength > declaredLength ||
			declaredLength > file.Length)
		{
			throw new InvalidDataException(
				"RSOUND.CVL has an invalid MZ length or header.");
		}

		return file
			.AsSpan(headerLength, declaredLength - headerLength)
			.ToArray();
	}

	private static (int DataBase, int TuneTable) ReadDispatcherLayout(
		byte[] module,
		int playFunction)
	{
		EnsureRange(module, playFunction, 1);
		int end = Math.Min(module.Length, checked(playFunction + 96));
		int dataSegment = -1;
		int tuneTable = -1;

		for (int position = playFunction;
			position < end;
			position++)
		{
			if (position + 5 <= end &&
				module[position] == 0xb8 &&
				module[position + 3] == 0x8e &&
				module[position + 4] == 0xd8)
			{
				dataSegment = ReadUInt16(module, position + 1);
			}

			if (position + 5 <= end &&
				module[position] == 0x2e &&
				module[position + 1] == 0xff &&
				module[position + 2] == 0x97)
			{
				tuneTable = ReadUInt16(module, position + 3);
			}
		}

		if (dataSegment < 0 || tuneTable < 0)
		{
			throw new InvalidDataException(
				"RSOUND.CVL play dispatcher was not recognized.");
		}

		return (checked(dataSegment * 16), tuneTable);
	}

	private static int ReadInt8BranchTarget(byte[] bytes, int displacement)
	{
		EnsureRange(bytes, displacement, 2);
		int relative = unchecked((sbyte)bytes[displacement + 1]);
		return checked(displacement + 2 + relative);
	}

	private static ushort RotateRight(ushort value, int count)
	{
		return (ushort)(
			(value >> count) |
			(value << (16 - count)));
	}

	private static int ReadUInt16(byte[] bytes, int offset)
	{
		EnsureRange(bytes, offset, 2);
		return bytes[offset] | (bytes[offset + 1] << 8);
	}

	private static void EnsureRange(
		byte[] bytes,
		int offset,
		int length)
	{
		if (offset < 0 ||
			length < 0 ||
			offset > bytes.Length - length)
		{
			throw new InvalidDataException(
				"RSOUND.CVL contains an out-of-range offset.");
		}
	}

	private readonly record struct TrackSetup(
		int TrackIndex,
		int StreamOffset);

	private sealed class TrackState
	{
		public TrackState(
			int channel,
			int setupChannel)
		{
			this.Channel = channel;
			this.SetupChannel = setupChannel;
		}

		public int Channel { get; }

		public int SetupChannel { get; }

		public bool Active { get; private set; }

		public byte RemainingTicks { get; set; }

		public byte NoteOffCountdown { get; set; }

		public byte Note { get; set; }

		public byte Velocity { get; set; }

		public byte Gate { get; set; }

		public byte Program { get; set; }

		public byte Volume { get; set; }

		public byte Pitch { get; set; }

		public byte Pan { get; set; }

		public sbyte VolumeStep { get; set; }

		public byte VolumeInterval { get; set; }

		public byte VolumeIntervalCountdown { get; set; }

		public sbyte PitchStep { get; set; }

		public byte PitchInterval { get; set; }

		public byte PitchIntervalCountdown { get; set; }

		public byte PitchStepCount { get; set; }

		public sbyte PanStep { get; set; }

		public byte PanInterval { get; set; }

		public byte PanIntervalCountdown { get; set; }

		public ushort OriginalStream { get; private set; }

		public ushort StreamPosition { get; set; }

		public ushort LoopStart { get; set; }

		public ushort NestedLoopStart { get; set; }

		public ushort LoopRemaining { get; set; }

		public ushort NestedLoopRemaining { get; set; }

		public int[] ActiveNotes { get; } = [-1, -1, -1, -1];

		public void Configure(int stream)
		{
			if (stream is < 0 or > ushort.MaxValue)
			{
				throw new InvalidDataException(
					"RSOUND stream is outside its 16-bit data segment.");
			}

			this.OriginalStream = (ushort)stream;
			this.ResetSequenceState(this.OriginalStream);
			this.RemainingTicks = 1;
			this.Active = true;
		}

		public void ResetSequenceState(ushort stream)
		{
			this.VolumeStep = 0;
			this.PitchStep = 0;
			this.PanStep = 0;
			this.Gate = 0;
			this.VolumeInterval = byte.MaxValue;
			this.Volume = 100;
			this.Pitch = 64;
			this.Pan = 64;
			this.LoopRemaining = 0;
			this.NestedLoopRemaining = 0;
			this.StreamPosition = stream;
			this.LoopStart = stream;
			this.NestedLoopStart = stream;
		}

		public void Deactivate()
		{
			this.Active = false;
			this.RemainingTicks = 0;
			this.NoteOffCountdown = 0;
			this.VolumeStep = 0;
			this.PitchStep = 0;
			this.PanStep = 0;
			Array.Fill(this.ActiveNotes, -1);
		}

		public void ExpireZeroDurationChord()
		{
			this.Active = false;
			this.VolumeStep = 0;
			this.PitchStep = 0;
			this.PanStep = 0;
		}
	}
}
