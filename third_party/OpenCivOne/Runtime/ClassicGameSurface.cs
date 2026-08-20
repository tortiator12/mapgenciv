using IRB.VirtualCPU;
using OpenCivOne.Graphics;
using OpenCivOne.Input;
using OpenCivOne.Platform;
using OpenCivOne.Presentation;

namespace OpenCivOne.Runtime;

/// <summary>
/// Platform-neutral host boundary for the imported Classic runtime.
/// </summary>
public sealed class ClassicGameSurface
{
	private readonly OpenCivOneGame game;
	private readonly ClassicRuntimeSession session;
	private readonly ClassicPointerInput pointerInput = new();
	private readonly ClassicRuntimePresentationProjection
		presentationProjection = new();
	private bool enableDiagnosticScreens;
	private int visibleScreenCount = -1;
	private int pointerX = ClassicPointerInput.LogicalWidth / 2;
	private int pointerY = ClassicPointerInput.LogicalHeight / 2;
	private ClassicCursorSnapshot lastCursor;

	public ClassicGameSurface(IClassicGameHost host)
		: this(host, ClassicRuntimeOptions.CreateDesktopDefault())
	{
	}

	public ClassicGameSurface(
		IClassicGameHost host,
		ClassicRuntimeOptions runtimeOptions)
		: this(
			host,
			runtimeOptions,
			new RolandCvlAudioSink(runtimeOptions))
	{
	}

	internal ClassicGameSurface(
		IClassicGameHost host,
		ClassicRuntimeOptions runtimeOptions,
		IClassicAudioSink audioSink)
	{
		ArgumentNullException.ThrowIfNull(host);
		ArgumentNullException.ThrowIfNull(runtimeOptions);
		ArgumentNullException.ThrowIfNull(audioSink);
		this.game = new OpenCivOneGame(
			host,
			runtimeOptions,
			audioSink);
		this.session = new ClassicRuntimeSession(this.game);
	}

	public ClassicRuntimeOptions RuntimeOptions => this.game.RuntimeOptions;

	public ClassicRuntimeState State => this.session.State;

	public Exception? Failure => this.session.Failure;

	public bool IsFinished => this.session.IsFinished;

	public bool IsPaused => this.game.CPU.Pause;

	public ClassicRuntimePresentationSnapshot CapturePresentationState() =>
		this.presentationProjection.Project(
			this.game.PresentationState.Capture(),
			allowInteractivePresentation:
				this.State == ClassicRuntimeState.Running &&
				!this.IsPaused &&
				!this.EnableDiagnosticScreens);

	public bool TryCaptureStablePresentationState(
		out ClassicRuntimePresentationSnapshot snapshot) =>
		this.game.PresentationState.TryCaptureStable(
			CapturePresentationState,
			out snapshot);

	public ClassicWorldMapViewportSnapshot? CaptureWorldMapViewport()
	{
		bool captured =
			this.game.PresentationState.TryCaptureStable(
			() =>
			{
				ClassicRuntimePresentationSnapshot before =
					CapturePresentationState();
				if (before.Kind is not
					(ClassicRuntimePresentationKind.InteractiveWorldMap or
						ClassicRuntimePresentationKind.WorldMapModalOverlay))
				{
					return null;
				}

				ClassicWorldMapViewportSnapshot? snapshot;
				lock (VCPU.GraphicsLock)
				{
					snapshot = ClassicWorldMapViewportCapture.TryCapture(
						this.game,
						before,
						CaptureWorldMapCursorSnapshot());
				}

				ClassicRuntimePresentationSnapshot after =
					CapturePresentationState();
				return before == after ? snapshot : null;
			},
			out ClassicWorldMapViewportSnapshot? snapshot);
		return captured ? snapshot : null;
	}

	/// <summary>
	/// Enables the original desktop host's multi-screen diagnostics. Product
	/// presentation remains fixed to the 320x200 primary screen by default.
	/// </summary>
	public bool EnableDiagnosticScreens
	{
		get => Volatile.Read(ref this.enableDiagnosticScreens);
		set
		{
			if (Volatile.Read(ref this.enableDiagnosticScreens) == value)
			{
				return;
			}

			Volatile.Write(ref this.enableDiagnosticScreens, value);
			Interlocked.Exchange(ref this.visibleScreenCount, -1);
		}
	}

	public void Start()
	{
		this.session.Start();
	}

	public void RequestStop()
	{
		this.session.RequestStop();
	}

	public bool Wait(TimeSpan timeout)
	{
		return this.session.Wait(timeout);
	}

	public bool SubmitPointer(
		int x,
		int y,
		int inputWidth,
		int inputHeight,
		MouseButtonsEnum buttons)
	{
		lock (OpenCivOneGame.KeyboardAndMouseLock)
		{
			bool queued = this.pointerInput.Submit(
				x,
				y,
				inputWidth,
				inputHeight,
				buttons,
				this.game.MouseEvents);

			if (x >= 0 && x < inputWidth && y >= 0 && y < inputHeight)
			{
				Volatile.Write(
					ref this.pointerX,
					(int)((long)x * ClassicPointerInput.LogicalWidth / inputWidth));
				Volatile.Write(
					ref this.pointerY,
					(int)((long)y * ClassicPointerInput.LogicalHeight / inputHeight));
			}

			return queued;
		}
	}

	public bool SubmitKey(
		ClassicHostKey key,
		ClassicKeyModifiers modifiers,
		char? symbol = null)
	{
		ClassicKeyTranslation translation =
			ClassicKeyTranslator.Translate(key, modifiers, symbol);

		lock (OpenCivOneGame.KeyboardAndMouseLock)
		{
			switch (translation.Action)
			{
				case ClassicKeyAction.EnqueueDosCode:
					this.game.Keys.Enqueue(translation.Value);
					break;

				case ClassicKeyAction.ToggleScreen:
					ToggleScreen(translation.Value);
					break;

				case ClassicKeyAction.TogglePause:
					this.game.CPU.Pause = !this.game.CPU.Pause;
					break;
			}
		}

		return translation.Handled;
	}

	public ClassicFrame? CaptureFrame(bool force = false)
	{
		lock (VCPU.GraphicsLock)
		{
			List<GBitmap> visibleScreens = [];
			bool needsRedraw = false;

			if (!this.EnableDiagnosticScreens)
			{
				if (this.game.Graphics.Screens.ContainsKey(0))
				{
					GBitmap primaryScreen =
						this.game.Graphics.Screens.GetValueByKey(0);
					visibleScreens.Add(primaryScreen);
					needsRedraw = primaryScreen.Modified;
				}
			}
			else
			{
				for (int i = 0; i < this.game.Graphics.Screens.Count; i++)
				{
					GBitmap screen = this.game.Graphics.Screens[i].Value;
					if (screen.Visible)
					{
						visibleScreens.Add(screen);
						needsRedraw |= screen.Modified;
					}
				}
			}

			ClassicCursorSnapshot cursor = CaptureCursorSnapshot();
			needsRedraw |= cursor != this.lastCursor;
			needsRedraw |= cursor.Bitmap?.Modified == true;

			if (this.visibleScreenCount != visibleScreens.Count)
			{
				this.visibleScreenCount = visibleScreens.Count;
				force = true;
			}

			if (!needsRedraw && !force)
			{
				return null;
			}

			ClassicScreenLayout layout =
				ClassicScreenLayout.ForVisibleScreenCount(visibleScreens.Count);
			ClassicFrame frame = ClassicFrameComposer.Compose(
				visibleScreens,
				layout.Columns,
				layout.Rows);

			if (cursor.Bitmap != null)
			{
				GBitmap targetScreen = visibleScreens.Count > 0
					? visibleScreens[0]
					: this.game.Graphics.Screens.GetValueByKey(0);
				ClassicCursorComposer.ComposeInPlace(
					frame,
					cursor.Bitmap,
					targetScreen.Palette,
					cursor.PointerX,
					cursor.PointerY,
					cursor.HotspotX,
					cursor.HotspotY);
				cursor.Bitmap.Modified = false;
			}

			foreach (GBitmap screen in visibleScreens)
			{
				screen.Modified = false;
			}

			this.lastCursor = cursor;
			return frame;
		}
	}

	private ClassicCursorSnapshot CaptureCursorSnapshot()
	{
		int cursorHandle = this.game.Var_5876_MouseIcon;
		GBitmap? cursor = this.game.Graphics.Bitmaps.ContainsKey(cursorHandle)
			? this.game.Graphics.Bitmaps.GetValueByKey(cursorHandle)
			: null;

		return cursor == null
			? default
			: new ClassicCursorSnapshot(
				cursor,
				Volatile.Read(ref this.pointerX),
				Volatile.Read(ref this.pointerY),
				this.game.Var_5878_MouseIconXOffset,
				this.game.Var_587a_MouseIconYOffset);
	}

	private ClassicWorldMapCursorSnapshot
		CaptureWorldMapCursorSnapshot()
	{
		ClassicCursorSnapshot cursor = CaptureCursorSnapshot();
		if (cursor.Bitmap == null)
		{
			return ClassicWorldMapCursorSnapshot.Hidden;
		}

		ClassicWorldMapCursorKind kind =
			this.game.Var_5876_MouseIcon ==
				this.game.Array_d4ce[2]
				? ClassicWorldMapCursorKind.Targeting
				: ClassicWorldMapCursorKind.Pointer;
		return ClassicWorldMapCursorSnapshot.Create(
			kind,
			cursor.PointerX,
			cursor.PointerY);
	}

	private void ToggleScreen(int screen)
	{
		if (!this.EnableDiagnosticScreens)
		{
			return;
		}

		if (this.game.Graphics.Screens.ContainsKey(screen))
		{
			GBitmap bitmap = this.game.Graphics.Screens.GetValueByKey(screen);
			bitmap.Visible = !bitmap.Visible;
		}
	}

	private readonly record struct ClassicCursorSnapshot(
		GBitmap? Bitmap,
		int PointerX,
		int PointerY,
		int HotspotX,
		int HotspotY);
}
