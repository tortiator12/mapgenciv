using IRB.VirtualCPU;

namespace OpenCivOne.Runtime;

/// <summary>
/// Owns the Classic runtime thread and exposes platform-neutral lifecycle
/// state for desktop and future mobile hosts.
/// </summary>
public sealed class ClassicRuntimeSession
{
	private readonly object sync = new();
	private readonly IClassicRuntimeProgram program;
	private Thread? thread;
	private volatile Exception? failure;
	private int state = (int)ClassicRuntimeState.Created;

	public ClassicRuntimeSession(IClassicRuntimeProgram program)
	{
		ArgumentNullException.ThrowIfNull(program);
		this.program = program;
	}

	public ClassicRuntimeState State =>
		(ClassicRuntimeState)Volatile.Read(ref this.state);

	public Exception? Failure => this.failure;

	public bool IsFinished =>
		this.State is ClassicRuntimeState.Completed or ClassicRuntimeState.Failed;

	public void Start()
	{
		lock (this.sync)
		{
			if (this.State != ClassicRuntimeState.Created)
			{
				throw new InvalidOperationException("The Classic runtime session can only be started once.");
			}

			this.thread = new Thread(Run)
			{
				Name = "OpenCivOne game thread",
				// A destroyed mobile Scene must never keep the process alive
				// if the platform terminates before the cooperative stop has
				// reached the emulated game loop.
				IsBackground = true,
			};
			Volatile.Write(ref this.state, (int)ClassicRuntimeState.Running);
			this.thread.Start();
		}
	}

	public void RequestStop()
	{
		lock (this.sync)
		{
			if (this.State != ClassicRuntimeState.Running)
			{
				return;
			}

			Volatile.Write(ref this.state, (int)ClassicRuntimeState.StopRequested);
		}

		this.program.RequestStop();
	}

	public bool Wait(TimeSpan timeout)
	{
		ArgumentOutOfRangeException.ThrowIfLessThan(timeout, TimeSpan.Zero);

		Thread? currentThread = this.thread;
		return currentThread == null
			? this.IsFinished
			: currentThread.Join(timeout);
	}

	private void Run()
	{
		try
		{
			this.program.Start();
			Complete();
		}
		catch (ApplicationExitException)
		{
			Complete();
		}
		catch (ResourceMissingException ex)
		{
			Fail(ex);
		}
#if !DEBUG
		catch (Exception ex)
		{
			Fail(ex);
		}
#endif
	}

	private void Complete()
	{
		Volatile.Write(ref this.state, (int)ClassicRuntimeState.Completed);
	}

	private void Fail(Exception exception)
	{
		this.failure = exception;
		Volatile.Write(ref this.state, (int)ClassicRuntimeState.Failed);
	}
}
