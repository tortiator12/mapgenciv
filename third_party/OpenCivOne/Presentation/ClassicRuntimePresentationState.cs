namespace OpenCivOne.Presentation;

/// <summary>
/// Conservative, presentation-only classification of the complete Classic
/// composition currently owned by the runtime.
/// </summary>
public enum ClassicRuntimePresentationKind
{
	Unknown,
	InteractiveWorldMap,
	WorldMapModalOverlay,
}

/// <summary>
/// Immutable observation of the runtime presentation lifecycle.
/// </summary>
public readonly record struct ClassicRuntimePresentationSnapshot(
	ClassicRuntimePresentationKind Kind,
	long Revision,
	int PlayerID = -1,
	int ActiveUnitID = -1,
	bool IsEndOfTurnPrompt = false);

/// <summary>
/// Thread-safe lifecycle signal shared by the runtime thread and platform
/// presenters. Unknown is the fail-safe state for every unclassified screen,
/// overlay, transition and error path.
/// </summary>
public sealed class ClassicRuntimePresentationState
{
	private readonly object sync = new();
	private readonly object semanticCaptureGate = new();
	private ClassicRuntimePresentationKind kind =
		ClassicRuntimePresentationKind.Unknown;
	private int playerID = -1;
	private int activeUnitID = -1;
	private bool isEndOfTurnPrompt;
	private long revision;

	public ClassicRuntimePresentationSnapshot Capture()
	{
		lock (this.sync)
		{
			return new ClassicRuntimePresentationSnapshot(
				this.kind,
				this.revision,
				this.playerID,
				this.activeUnitID,
				this.isEndOfTurnPrompt);
		}
	}

	internal void MarkInteractiveWorldMap(
		int playerID,
		int activeUnitID,
		bool isEndOfTurnPrompt = false) =>
		SetState(
			ClassicRuntimePresentationKind.InteractiveWorldMap,
			playerID,
			activeUnitID,
			isEndOfTurnPrompt);

	internal void MarkWorldMapModalOverlay(
		int playerID,
		int activeUnitID) =>
		SetState(
			ClassicRuntimePresentationKind.WorldMapModalOverlay,
			playerID,
			activeUnitID,
			nextIsEndOfTurnPrompt: false);

	internal void MarkUnknown() =>
		SetState(
			ClassicRuntimePresentationKind.Unknown,
			nextPlayerID: -1,
			nextActiveUnitID: -1,
			nextIsEndOfTurnPrompt: false);

	internal ClassicRuntimeMutationLease EnterRuntimeMutation() =>
		new(this);

	internal bool TryCaptureStable<T>(
		Func<T> capture,
		out T result)
	{
		ArgumentNullException.ThrowIfNull(capture);
		if (!Monitor.TryEnter(this.semanticCaptureGate))
		{
			result = default!;
			return false;
		}

		try
		{
			result = capture();
			return true;
		}
		finally
		{
			Monitor.Exit(this.semanticCaptureGate);
		}
	}

	private void EnterSemanticMutation() =>
		Monitor.Enter(this.semanticCaptureGate);

	private void ExitSemanticMutation() =>
		Monitor.Exit(this.semanticCaptureGate);

	private void SetState(
		ClassicRuntimePresentationKind nextKind,
		int nextPlayerID,
		int nextActiveUnitID,
		bool nextIsEndOfTurnPrompt)
	{
		lock (this.sync)
		{
			if (this.kind == nextKind &&
				this.playerID == nextPlayerID &&
				this.activeUnitID == nextActiveUnitID &&
				this.isEndOfTurnPrompt ==
					nextIsEndOfTurnPrompt)
			{
				return;
			}

			this.kind = nextKind;
			this.playerID = nextPlayerID;
			this.activeUnitID = nextActiveUnitID;
			this.isEndOfTurnPrompt =
				nextIsEndOfTurnPrompt;
			checked
			{
				this.revision++;
			}
		}
	}

	internal sealed class ClassicRuntimeMutationLease : IDisposable
	{
		private readonly ClassicRuntimePresentationState owner;
		private bool ownsMutationGate;
		private bool disposed;

		internal ClassicRuntimeMutationLease(
			ClassicRuntimePresentationState owner)
		{
			this.owner = owner;
			this.owner.EnterSemanticMutation();
			this.ownsMutationGate = true;
			this.owner.MarkUnknown();
		}

		internal void PublishInteractiveAndRelease(
			int playerID,
			int activeUnitID,
			bool isEndOfTurnPrompt = false)
		{
			ThrowIfDisposed();
			if (!this.ownsMutationGate)
			{
				throw new InvalidOperationException(
					"The runtime mutation gate is already released.");
			}

			this.owner.MarkInteractiveWorldMap(
				playerID,
				activeUnitID,
				isEndOfTurnPrompt);
			this.owner.ExitSemanticMutation();
			this.ownsMutationGate = false;
		}

		internal void ReacquireAndMarkUnknown()
		{
			ThrowIfDisposed();
			if (this.ownsMutationGate)
			{
				throw new InvalidOperationException(
					"The runtime mutation gate is already held.");
			}

			this.owner.EnterSemanticMutation();
			this.ownsMutationGate = true;
			this.owner.MarkUnknown();
		}

		internal void RunInteractiveWorldMapAnimation(
			int playerID,
			int activeUnitID,
			Action animation)
		{
			ArgumentNullException.ThrowIfNull(animation);
			PublishInteractiveAndRelease(playerID, activeUnitID);
			try
			{
				animation();
			}
			finally
			{
				ReacquireAndMarkUnknown();
			}
		}

		internal T RunWorldMapModalOverlay<T>(
			int playerID,
			int activeUnitID,
			Func<T> showDialog)
		{
			ArgumentNullException.ThrowIfNull(showDialog);
			PublishWorldMapModalAndRelease(playerID, activeUnitID);
			try
			{
				return showDialog();
			}
			finally
			{
				ReacquireAndMarkUnknown();
			}
		}

		internal void RunWorldMapModalOverlay(
			int playerID,
			int activeUnitID,
			Action showDialog) =>
			RunWorldMapModalOverlay(
				playerID,
				activeUnitID,
				() =>
				{
					showDialog();
					return true;
				});

		public void Dispose()
		{
			if (this.disposed)
			{
				return;
			}

			this.disposed = true;
			if (this.ownsMutationGate)
			{
				this.owner.ExitSemanticMutation();
				this.ownsMutationGate = false;
			}
		}

		private void ThrowIfDisposed()
		{
			ObjectDisposedException.ThrowIf(
				this.disposed,
				this);
		}

		private void PublishWorldMapModalAndRelease(
			int playerID,
			int activeUnitID)
		{
			ThrowIfDisposed();
			if (!this.ownsMutationGate)
			{
				throw new InvalidOperationException(
					"The runtime mutation gate is already released.");
			}

			this.owner.MarkWorldMapModalOverlay(
				playerID,
				activeUnitID);
			this.owner.ExitSemanticMutation();
			this.ownsMutationGate = false;
		}
	}
}

/// <summary>
/// Projects the runtime-owned screen state through host lifecycle gates and
/// publishes its own monotonic revision for presentation caches.
/// </summary>
public sealed class ClassicRuntimePresentationProjection
{
	private readonly object sync = new();
	private bool initialized;
	private ClassicRuntimePresentationKind lastKind;
	private int lastPlayerID = -1;
	private int lastActiveUnitID = -1;
	private bool lastIsEndOfTurnPrompt;
	private long lastRuntimeRevision;
	private long revision;

	public ClassicRuntimePresentationSnapshot Project(
		ClassicRuntimePresentationSnapshot runtimeSnapshot,
		bool allowInteractivePresentation)
	{
		ClassicRuntimePresentationKind projectedKind =
			allowInteractivePresentation
				? runtimeSnapshot.Kind
				: ClassicRuntimePresentationKind.Unknown;
		bool hasInteractiveContext =
			projectedKind is
				ClassicRuntimePresentationKind.InteractiveWorldMap or
				ClassicRuntimePresentationKind.WorldMapModalOverlay;
		int projectedPlayerID =
			hasInteractiveContext
				? runtimeSnapshot.PlayerID
				: -1;
		int projectedActiveUnitID =
			hasInteractiveContext
				? runtimeSnapshot.ActiveUnitID
				: -1;
		bool projectedIsEndOfTurnPrompt =
			hasInteractiveContext &&
			runtimeSnapshot.IsEndOfTurnPrompt;

		lock (this.sync)
		{
			if (!this.initialized)
			{
				this.initialized = true;
				this.lastKind = projectedKind;
				this.lastPlayerID = projectedPlayerID;
				this.lastActiveUnitID = projectedActiveUnitID;
				this.lastIsEndOfTurnPrompt =
					projectedIsEndOfTurnPrompt;
				this.lastRuntimeRevision = runtimeSnapshot.Revision;
				this.revision = runtimeSnapshot.Revision;
			}
			else if (this.lastKind != projectedKind ||
				this.lastPlayerID != projectedPlayerID ||
				this.lastActiveUnitID != projectedActiveUnitID ||
				this.lastIsEndOfTurnPrompt !=
					projectedIsEndOfTurnPrompt ||
				this.lastRuntimeRevision != runtimeSnapshot.Revision)
			{
				this.lastKind = projectedKind;
				this.lastPlayerID = projectedPlayerID;
				this.lastActiveUnitID = projectedActiveUnitID;
				this.lastIsEndOfTurnPrompt =
					projectedIsEndOfTurnPrompt;
				this.lastRuntimeRevision = runtimeSnapshot.Revision;
				checked
				{
					this.revision = Math.Max(
						this.revision + 1,
						runtimeSnapshot.Revision);
				}
			}

			return new ClassicRuntimePresentationSnapshot(
				projectedKind,
				this.revision,
				projectedPlayerID,
				projectedActiveUnitID,
				projectedIsEndOfTurnPrompt);
		}
	}
}
