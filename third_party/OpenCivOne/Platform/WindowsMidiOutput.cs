namespace OpenCivOne.Platform;

/// <summary>
/// Reports a failed WinMM MIDI-out operation.
/// </summary>
public sealed class WindowsMidiOutputException : InvalidOperationException
{
	internal WindowsMidiOutputException(
		string operation,
		uint resultCode,
		string nativeMessage)
		: base(
			$"WinMM MIDI operation '{operation}' failed with code " +
			$"{resultCode}: {nativeMessage}")
	{
		this.Operation = operation;
		this.ResultCode = resultCode;
	}

	public string Operation { get; }

	public uint ResultCode { get; }
}

/// <summary>
/// Thread-safe short-message output for the Windows MIDI mapper.
/// </summary>
/// <remarks>
/// Call <see cref="Open()"/> before sending messages. All MIDI values use
/// their protocol ranges: channels 0-15, data bytes 0-127 and pitch bend
/// 0-16383 with 8192 as the center position.
/// </remarks>
public sealed class WindowsMidiOutput : IDisposable
{
	private const uint NoError = 0;
	private const int ChannelCount = 16;
	private const int MaximumDataByte = 127;
	private const int MaximumPitchBend = 16383;
	private const int AllNotesOffController = 123;
	private const byte NoteOffStatus = 0x80;
	private const byte NoteOnStatus = 0x90;
	private const byte ControlChangeStatus = 0xb0;
	private const byte ProgramChangeStatus = 0xc0;
	private const byte PitchBendStatus = 0xe0;

	private readonly object synchronization = new();
	private readonly IWindowsMidiOutNative native;
	private nint handle;
	private bool isOpen;
	private bool isDisposed;

	public WindowsMidiOutput()
		: this(new WinMmMidiOutNative())
	{
	}

	/// <summary>
	/// Creates an output over an injected native boundary. This constructor
	/// supports deterministic tests and alternate WinMM adapters.
	/// </summary>
	public WindowsMidiOutput(IWindowsMidiOutNative native)
	{
		ArgumentNullException.ThrowIfNull(native);
		this.native = native;
	}

	/// <summary>
	/// WinMM's MIDI_MAPPER device identifier.
	/// </summary>
	public const uint DefaultDeviceId = uint.MaxValue;

	public bool IsAvailable => this.native.IsSupported;

	public bool IsOpen
	{
		get
		{
			lock (this.synchronization)
			{
				return this.isOpen;
			}
		}
	}

	/// <summary>
	/// Opens the Windows default MIDI output device.
	/// </summary>
	public void Open()
	{
		lock (this.synchronization)
		{
			this.ThrowIfDisposed();
			if (this.isOpen)
			{
				return;
			}

			if (!this.native.IsSupported)
			{
				throw new PlatformNotSupportedException(
					"WinMM MIDI output is available only on Windows.");
			}

			uint result = this.native.Open(
				out nint openedHandle,
				DefaultDeviceId);
			this.ThrowIfNativeFailed("open", result);
			this.handle = openedHandle;
			this.isOpen = true;
		}
	}

	public void NoteOn(int channel, int note, int velocity)
	{
		ValidateChannel(channel);
		ValidateDataByte(note, nameof(note));
		ValidateDataByte(velocity, nameof(velocity));
		this.SendChannelMessage(
			NoteOnStatus,
			channel,
			note,
			velocity);
	}

	public void NoteOff(int channel, int note, int velocity)
	{
		ValidateChannel(channel);
		ValidateDataByte(note, nameof(note));
		ValidateDataByte(velocity, nameof(velocity));
		this.SendChannelMessage(
			NoteOffStatus,
			channel,
			note,
			velocity);
	}

	public void ProgramChange(int channel, int program)
	{
		ValidateChannel(channel);
		ValidateDataByte(program, nameof(program));
		this.SendChannelMessage(
			ProgramChangeStatus,
			channel,
			program,
			0);
	}

	public void ControlChange(int channel, int controller, int value)
	{
		ValidateChannel(channel);
		ValidateDataByte(controller, nameof(controller));
		ValidateDataByte(value, nameof(value));
		this.SendChannelMessage(
			ControlChangeStatus,
			channel,
			controller,
			value);
	}

	public void PitchBend(int channel, int value)
	{
		ValidateChannel(channel);
		if (value is < 0 or > MaximumPitchBend)
		{
			throw new ArgumentOutOfRangeException(
				nameof(value),
				value,
				$"Pitch bend must be between 0 and " +
				$"{MaximumPitchBend}.");
		}

		int leastSignificant = value & MaximumDataByte;
		int mostSignificant = (value >> 7) & MaximumDataByte;
		this.SendChannelMessage(
			PitchBendStatus,
			channel,
			leastSignificant,
			mostSignificant);
	}

	public void AllNotesOff(int channel)
	{
		ValidateChannel(channel);
		this.ControlChange(channel, AllNotesOffController, 0);
	}

	/// <summary>
	/// Sends MIDI All Notes Off to every channel as one synchronized batch.
	/// </summary>
	public void AllNotesOff()
	{
		lock (this.synchronization)
		{
			this.ThrowIfDisposed();
			this.ThrowIfClosed();
			for (int channel = 0; channel < ChannelCount; channel++)
			{
				this.SendChannelMessageCore(
					ControlChangeStatus,
					channel,
					AllNotesOffController,
					0);
			}
		}
	}

	/// <summary>
	/// Stops all pending and sounding output on the opened WinMM device.
	/// </summary>
	public void Reset()
	{
		lock (this.synchronization)
		{
			this.ThrowIfDisposed();
			this.ThrowIfClosed();
			uint result = this.native.Reset(this.handle);
			this.ThrowIfNativeFailed("reset", result);
		}
	}

	/// <summary>
	/// Resets and closes the device. The close call is still attempted when
	/// reset fails, preventing a reset error from leaking the native handle.
	/// </summary>
	public void Close()
	{
		lock (this.synchronization)
		{
			if (!this.isOpen)
			{
				return;
			}

			Exception? failure = this.CloseCore();
			if (failure is not null)
			{
				throw failure;
			}
		}
	}

	public void Dispose()
	{
		lock (this.synchronization)
		{
			if (this.isDisposed)
			{
				return;
			}

			Exception? failure = this.isOpen
				? this.CloseCore()
				: null;
			if (!this.isOpen)
			{
				this.isDisposed = true;
			}

			if (failure is not null)
			{
				throw failure;
			}
		}
	}

	private void SendChannelMessage(
		byte status,
		int channel,
		int firstData,
		int secondData)
	{
		lock (this.synchronization)
		{
			this.ThrowIfDisposed();
			this.ThrowIfClosed();
			this.SendChannelMessageCore(
				status,
				channel,
				firstData,
				secondData);
		}
	}

	private void SendChannelMessageCore(
		byte status,
		int channel,
		int firstData,
		int secondData)
	{
		uint message =
			(uint)(status | channel) |
			((uint)firstData << 8) |
			((uint)secondData << 16);
		uint result = this.native.SendShortMessage(
			this.handle,
			message);
		this.ThrowIfNativeFailed("send short message", result);
	}

	private Exception? CloseCore()
	{
		Exception? resetFailure = null;
		Exception? closeFailure = null;

		try
		{
			uint resetResult = this.native.Reset(this.handle);
			this.ThrowIfNativeFailed("reset", resetResult);
		}
		catch (Exception exception)
		{
			resetFailure = exception;
		}

		try
		{
			uint closeResult = this.native.Close(this.handle);
			this.ThrowIfNativeFailed("close", closeResult);
			this.handle = nint.Zero;
			this.isOpen = false;
		}
		catch (Exception exception)
		{
			closeFailure = exception;
		}

		if (resetFailure is not null && closeFailure is not null)
		{
			return new AggregateException(
				"WinMM MIDI reset and close both failed.",
				resetFailure,
				closeFailure);
		}

		return closeFailure ?? resetFailure;
	}

	private void ThrowIfNativeFailed(string operation, uint result)
	{
		if (result == NoError)
		{
			return;
		}

		string message;
		try
		{
			message = this.native.GetErrorText(result);
		}
		catch (Exception errorTextFailure)
		{
			message =
				$"The native error text could not be read " +
				$"({errorTextFailure.GetType().Name}).";
		}

		throw new WindowsMidiOutputException(
			operation,
			result,
			message);
	}

	private void ThrowIfClosed()
	{
		if (!this.isOpen)
		{
			throw new InvalidOperationException(
				"The MIDI output device is not open.");
		}
	}

	private void ThrowIfDisposed()
	{
		ObjectDisposedException.ThrowIf(
			this.isDisposed,
			this);
	}

	private static void ValidateChannel(int channel)
	{
		if (channel is < 0 or >= ChannelCount)
		{
			throw new ArgumentOutOfRangeException(
				nameof(channel),
				channel,
				$"MIDI channel must be between 0 and " +
				$"{ChannelCount - 1}.");
		}
	}

	private static void ValidateDataByte(int value, string parameterName)
	{
		if (value is < 0 or > MaximumDataByte)
		{
			throw new ArgumentOutOfRangeException(
				parameterName,
				value,
				$"MIDI data must be between 0 and " +
				$"{MaximumDataByte}.");
		}
	}
}
