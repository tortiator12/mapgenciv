using IRB.VirtualCPU;
using OpenCivOne.Platform;

namespace OpenCivOne
{
	public class NSound
	{
		private readonly OpenCivOneGame parent;
		private readonly VCPU CPU;
		private readonly IClassicAudioSink audioSink;
		private readonly object audioDiagnosticLock = new();
		private readonly object audioLifecycleLock = new();
		private int audioSinkClosed;
		private int audioSinkFailed;
		private int audioSinkInitialized;
		private int normalTickPhase;
		private ushort bufferPosition = 0;

		public NSound(
			OpenCivOneGame parent,
			IClassicAudioSink audioSink)
		{
			ArgumentNullException.ThrowIfNull(parent);
			this.parent = parent;
			this.audioSink =
				audioSink ?? throw new ArgumentNullException(nameof(audioSink));
			this.CPU = parent.CPU;
		}

		public bool IsAvailable
		{
			get
			{
				if (Volatile.Read(ref this.audioSinkFailed) != 0)
				{
					return false;
				}

				try
				{
					return this.audioSink.IsAvailable;
				}
				catch (Exception exception)
				{
					HandleAudioSinkFailure("availability", exception);
					return false;
				}
			}
		}

		public char DriverType => this.IsAvailable ? 'A' : 'N';

		/// <summary>
		/// ?
		/// </summary>
		/// <returns></returns>
		public ushort F0_0000_0048_InitSound()
		{
			//this.oCPU.Log.EnterBlock("'F0_0000_0048_InitSound'(Cdecl, Far) at 0x0000:0x0048");

			lock (this.audioLifecycleLock)
			{
				// function body
				bufferPosition = 0;
				this.normalTickPhase = 0;
				Volatile.Write(ref this.audioSinkClosed, 0);
				Volatile.Write(ref this.audioSinkFailed, 0);
				Volatile.Write(ref this.audioSinkInitialized, 0);
				if (this.IsAvailable)
				{
					InvokeAudioSink(
						"initialize",
						this.audioSink.Initialize);
					if (Volatile.Read(ref this.audioSinkFailed) == 0)
					{
						Volatile.Write(
							ref this.audioSinkInitialized,
							1);
					}
				}
				this.CPU.AX.UInt16 = 0;
			}

			return this.CPU.AX.UInt16;
		}

		/// <summary>
		/// ?
		/// </summary>
		/// <returns></returns>
		public ushort F0_0000_0055_SoundWorker()
		{
			//this.oCPU.Log.EnterBlock("'F0_0000_0055_SoundWorker'(Cdecl, Far) at 0x0000:0x0055");

			// function body
			// OpenCivOne's shared presentation timer currently fires at
			// 100 Hz. Keep the original-facing compatibility counter and sink
			// health pulse at an average 60 Hz without changing palette or
			// pointer timing. Timing-sensitive sinks may own a more precise
			// monotonic clock away from this presentation callback.
			this.normalTickPhase += 3;
			if (this.normalTickPhase < 5)
			{
				return 0;
			}
			this.normalTickPhase -= 5;
			bufferPosition++;
			if (this.parent.GameData.GameSettingFlags.Sound &&
				Volatile.Read(ref this.audioSinkClosed) == 0 &&
				Volatile.Read(ref this.audioSinkFailed) == 0 &&
				Volatile.Read(ref this.audioSinkInitialized) != 0)
			{
				InvokeAudioSink("advance", this.audioSink.AdvanceTick);
			}
			
			return 0;
		}

		/// <summary>
		/// ?
		/// </summary>
		public void F0_0000_005c_FastSoundWorker()
		{
			//this.oCPU.Log.EnterBlock("'F0_0000_005c_FastSoundWorker'(Cdecl, Far) at 0x0000:0x005c");

			// function body
		}

		/// <summary>
		/// ?
		/// </summary>
		/// <returns></returns>
		public ushort F0_0000_005d_SoundTimer()
		{
			//this.oCPU.Log.EnterBlock("'F0_0000_005d_SoundTimer'(Cdecl, Far) at 0x0000:0x005d");

			// function body
			this.CPU.AX.UInt16 = bufferPosition;

			return this.CPU.AX.UInt16;
		}

		/// <summary>
		/// ?
		/// </summary>
		/// <param name="tune"></param>
		/// <param name="param2"></param>
		public void F0_0000_0062_PlayTune(short tune, ushort param2)
		{
			//this.oCPU.Log.EnterBlock("'F0_0000_0062_PlayTune'(Cdecl, Far) at 0x0000:0x0062");

			// function body
			bufferPosition = 0;
			if (this.parent.GameData.GameSettingFlags.Sound &&
				Volatile.Read(ref this.audioSinkClosed) == 0 &&
				Volatile.Read(ref this.audioSinkFailed) == 0 &&
				Volatile.Read(ref this.audioSinkInitialized) != 0)
			{
				InvokeAudioSink(
					"play",
					() => this.audioSink.PlayTune(tune, param2));
			}
		}

		/// <summary>
		/// Stops audible output without changing the legacy compatibility
		/// timer. This command is intentionally independent from the Sound
		/// setting so disabling sound can never suppress its own stop.
		/// </summary>
		public void Stop()
		{
			if (Volatile.Read(ref this.audioSinkClosed) == 0 &&
				Volatile.Read(ref this.audioSinkInitialized) != 0)
			{
				InvokeAudioSink("stop", this.audioSink.Stop);
			}
		}

		/// <summary>
		/// ?
		/// </summary>
		/// <returns></returns>
		public ushort F0_0000_006a_CloseSound()
		{
			//this.oCPU.Log.EnterBlock("'F0_0000_006a_CloseSound'(Cdecl, Far) at 0x0000:0x006a");

			// function body
			lock (this.audioLifecycleLock)
			{
				if (Volatile.Read(ref this.audioSinkClosed) == 0 &&
					InvokeAudioSink("close", this.audioSink.Close))
				{
					Interlocked.Exchange(ref this.audioSinkClosed, 1);
				}
			}
			Volatile.Write(ref this.audioSinkInitialized, 0);
			this.CPU.AX.UInt16 = 0;

			return this.CPU.AX.UInt16;
		}

		private bool InvokeAudioSink(string operation, Action action)
		{
			try
			{
				action();
				return true;
			}
			catch (Exception exception)
			{
				HandleAudioSinkFailure(operation, exception);
				return false;
			}
		}

		private void HandleAudioSinkFailure(
			string operation,
			Exception exception)
		{
			Volatile.Write(ref this.audioSinkFailed, 1);
			this.parent.Var_1a30_SoundDriverType = 'N';
			this.parent.GameData.GameSettingFlags.Sound = false;
			bool wasInitialized =
				Interlocked.Exchange(
					ref this.audioSinkInitialized,
					0) != 0;
			List<Exception> cleanupFailures = [];
			lock (this.audioLifecycleLock)
			{
				if (operation != "close" &&
					Volatile.Read(ref this.audioSinkClosed) == 0)
				{
					if (wasInitialized && operation != "stop")
					{
						try
						{
							this.audioSink.Stop();
						}
						catch (Exception cleanupFailure)
						{
							cleanupFailures.Add(cleanupFailure);
						}
					}

					try
					{
						this.audioSink.Close();
						Interlocked.Exchange(
							ref this.audioSinkClosed,
							1);
					}
					catch (Exception cleanupFailure)
					{
						cleanupFailures.Add(cleanupFailure);
					}
				}
			}

			string diagnostic =
				$"Classic audio sink {operation} failed: " +
				$"{exception.GetType().Name}: {exception.Message}";
			if (cleanupFailures.Count > 0)
			{
				diagnostic +=
					$" Cleanup also reported " +
					$"{cleanupFailures.Count} failure(s): " +
					string.Join(
						" | ",
						cleanupFailures.Select(
							failure =>
								$"{failure.GetType().Name}: " +
								failure.Message));
			}

			try
			{
				this.parent.Log.WriteLine(diagnostic);
			}
			catch (Exception)
			{
				// Audio diagnostics must not turn an optional sink failure into
				// a Classic runtime failure.
			}

			try
			{
				lock (this.audioDiagnosticLock)
				{
					File.AppendAllText(
						this.parent.RuntimeOptions.GetLogFilePath("Audio.log"),
						$"[{DateTimeOffset.Now:O}] {diagnostic}" +
							Environment.NewLine);
				}
			}
			catch (Exception)
			{
				// The writable diagnostic path is best effort. Failure to log an
				// optional audio error must never affect Classic gameplay.
			}
		}
	}
}
