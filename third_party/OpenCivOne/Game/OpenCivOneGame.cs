using Avalonia.Controls;
using IRB.VirtualCPU;
using OpenCivOne.Graphics;
using OpenCivOne.Platform;
using OpenCivOne.Presentation;
using OpenCivOne.Resources;
using OpenCivOne.Runtime;
using System.Diagnostics;

namespace OpenCivOne
{
	public partial class OpenCivOneGame : IClassicRuntimeProgram
	{
		public static readonly GPoint InvalidPosition = new GPoint(-1);

		private static bool enableLog = false;

		private readonly IClassicGameHost host;
		private VCPU oCPU;

		#region Segment definitions
		private StartGame startGame;
		private CommonTools commonTools;
		private Segment_1238 oSegment_1238;
		private MenuBoxDialog menuBoxDialog;
		private PlayerTurn playerTurn;
		private Tools tools;
		private DrawTools drawTools;
		private ImageTools imageTools;
		private LanguageTools languageTools;
		private MapManagement mapManagement;
		private UnitManagement unitManagement;
		private UnitGoTo unitGoTo;
		private Actions oSegment_2459;
		private AIEngine aiEngine;
		private Segment_1ade oSegment_1ade;
		private CityWorker cityWorker;
		private AttackActions oSegment_29f3;
		private Segment_2517 oSegment_2517;
		private Menus menus;
		private MainIntro mainIntro;
		private MeetWithKing meetWithKing;
		private MapInitAndIntro mapInitAndIntro;
		private Help help;
		private LoadAndSave loadAndSave;
		private HallOfFame hallOfFame;
		private StartGameMenu startGameMenu;
		private TextBoxDialogs textBoxDialogs;
		private Overlay_14 oOverlay_14;
		private Encyclopedia encyclopedia;
		private News news;
		private CityView cityView;
		private Overlay_18 oOverlay_18;
		private Overlay_22 oOverlay_22;
		private Replay replay;
		private Reports reports;
		private Overlay_20 oOverlay_20;
		private Palace palace;
		private ShowDebugDetails showDebugDetails;
		private Secession secession;
		private CAPI CApi;
		private GDriver graphics;
		private NSound sound;
		#endregion

		private LogWrapper oLog;
		private LogWrapper oInterruptLog;
		private LogWrapper oGoToLog;

		private ushort usStartSegment = 0x1000;

		private GameData gameData;
		private readonly ClassicUnitAutomationState
			unitAutomationState;
		private readonly ClassicRuntimePresentationState
			presentationState;

		private readonly ClassicRuntimeOptions runtimeOptions;
		private readonly ClassicRuntimeFileResolver runtimeFiles;
		private string gameResourcePath = "";
		private string gameMainPath = "";
		private string gameSavePath = "";

		// Keyboard
		public static readonly object KeyboardAndMouseLock = new();
		private Queue<int> keys = new Queue<int>();
		private int automaticEndTurnPauseRequested;
		private int automaticEndTurnPauseCaptureEnabled;

		// Mouse
		private List<MouseEvent> mouseEvents = new List<MouseEvent>();
		private MouseEvent lastMouseEvent = new MouseEvent(new GPoint(160, 100), MouseButtonsEnum.None);

		public OpenCivOneGame(IClassicGameHost host)
			: this(
				host,
				ClassicRuntimeOptions.CreateDesktopDefault(),
				NullClassicAudioSink.Instance)
		{
		}

		public OpenCivOneGame(
			IClassicGameHost host,
			ClassicRuntimeOptions runtimeOptions)
			: this(host, runtimeOptions, NullClassicAudioSink.Instance)
		{
		}

		public OpenCivOneGame(
			IClassicGameHost host,
			ClassicRuntimeOptions runtimeOptions,
			IClassicAudioSink audioSink)
		{
			this.host = host ?? throw new ArgumentNullException(nameof(host));
			this.runtimeOptions =
				runtimeOptions ?? throw new ArgumentNullException(nameof(runtimeOptions));
			ArgumentNullException.ThrowIfNull(audioSink);
			this.runtimeFiles = new ClassicRuntimeFileResolver(this.runtimeOptions);

			try
			{
				this.gameResourcePath = this.runtimeOptions.ResourcePath;
				this.gameSavePath = this.runtimeOptions.SavePath;
				this.gameMainPath =
					Path.GetDirectoryName(
						Path.TrimEndingDirectorySeparator(this.gameSavePath))
					?? Path.TrimEndingDirectorySeparator(this.gameSavePath);

				// Only writable runtime directories are created here. The
				// original resource directory is supplied by the user and is
				// never created or modified by OpenCivOne.
				Directory.CreateDirectory(this.gameSavePath);
				Directory.CreateDirectory(this.runtimeOptions.LogPath);
			}
			catch (Exception e)
			{
				throw new Exception($"Could not create necessary game paths. The error is '{e.Message}'");
			}

			this.oLog = new LogWrapper(
				this.runtimeOptions.GetLogFilePath("Log.txt"),
				enableLog);
			this.oInterruptLog = new LogWrapper(
				this.runtimeOptions.GetLogFilePath("InterruptLog.txt"),
				enableLog);
			this.oGoToLog = new LogWrapper(
				this.runtimeOptions.GetLogFilePath("GoToLog.txt"),
				enableLog);

			this.oCPU = new VCPU(this, this.oLog);

			this.oLog.CPU = this.oCPU;
			this.oInterruptLog.CPU = this.oCPU;
			this.oGoToLog.CPU = this.oCPU;

			this.gameData = new GameData();
			this.unitAutomationState =
				new ClassicUnitAutomationState();
			this.presentationState =
				new ClassicRuntimePresentationState();

			#region Initialize Segments
			this.CApi = new CAPI(this);
			this.graphics = new GDriver(this);
			this.sound = new NSound(this, audioSink);

			this.startGame = new StartGame(this);
			this.commonTools = new CommonTools(this);
			this.oSegment_1238 = new Segment_1238(this);
			this.menuBoxDialog = new MenuBoxDialog(this);
			this.playerTurn = new PlayerTurn(this);
			this.tools = new Tools(this);
			this.drawTools = new DrawTools(this);
			this.imageTools = new ImageTools(this);
			this.languageTools = new LanguageTools(this);
			this.mapManagement = new MapManagement(this);
			this.unitManagement = new UnitManagement(this);
			this.unitGoTo = new UnitGoTo(this);
			this.oSegment_2459 = new Actions(this);
			this.aiEngine = new AIEngine(this);
			this.oSegment_1ade = new Segment_1ade(this);
			this.cityWorker = new CityWorker(this);
			this.oSegment_29f3 = new AttackActions(this);
			this.oSegment_2517 = new Segment_2517(this);
			this.menus = new Menus(this);
			this.mainIntro = new MainIntro(this);
			this.meetWithKing = new MeetWithKing(this);
			this.mapInitAndIntro = new MapInitAndIntro(this);
			this.help = new Help(this);
			this.loadAndSave = new LoadAndSave(this);
			this.hallOfFame = new HallOfFame(this);
			this.startGameMenu = new StartGameMenu(this);
			this.textBoxDialogs = new TextBoxDialogs(this);
			this.oOverlay_14 = new Overlay_14(this);
			this.encyclopedia = new Encyclopedia(this);
			this.news = new News(this);
			this.cityView = new CityView(this);
			this.oOverlay_18 = new Overlay_18(this);
			this.oOverlay_22 = new Overlay_22(this);
			this.replay = new Replay(this);
			this.reports = new Reports(this);
			this.oOverlay_20 = new Overlay_20(this);
			this.palace = new Palace(this);
			this.showDebugDetails = new ShowDebugDetails(this);
			this.secession = new Secession(this);
			#endregion

			/*string[] aFiles = Directory.GetFiles(this.oParent.ResourcePath, "*.pic");

			for (int i = 0; i < aFiles.Length; i++)
			{
				WriteImage(aFiles[i], @"Z:\Civilization\Images\" + Path.GetFileNameWithoutExtension(aFiles[i]) + ".png");
			}*/

			/*byte[] palette;
			var colors = GBitmap.ReadPaletteFromPICFile(@"Z:\Games\Civilization\Civ I\Dos\Installed\CIV1.5\sp256.pal", out palette);

			StreamWriter writer = new StreamWriter("palette.txt");

			for (int i = 0; i < colors.Count; i++)
			{
				Color color = colors[i].Value;

				writer.WriteLine($"new Color(0, {color.R}, {color.G}, {color.B}),");
			}

			writer.Close();*/
		}

		public void Start()
		{
			try
			{
				StartCore();
			}
			finally
			{
				this.presentationState.MarkUnknown();
				// The legacy StartGame path also closes on a normal ending.
				// Keeping cleanup here covers validation failures, runtime
				// exceptions and the cooperative RequestStop unwind.
				this.CommonTools.CloseSoundEngine();
				this.CommonTools.StopGameMainTimer();
			}
		}

		private void StartCore()
		{
			#region Check if all resources are present
			// Check for Default directory and individual Resource files
			if (!string.IsNullOrEmpty(this.gameResourcePath) && !Directory.Exists(this.gameResourcePath))
			{
				throw new ResourceMissingException($"Resource path not found at '{this.gameResourcePath}'.");
			}

			ClassicDataValidationResult validation =
				ClassicDataSetValidator.Validate(
					this.runtimeOptions.ResourceProvider.AvailableFileNames);

			if (!validation.IsValid)
			{
				List<string> problems = [];
				if (validation.MissingRequiredFileNames.Count > 0)
				{
					problems.Add(
						$"Missing files: {string.Join(", ", validation.MissingRequiredFileNames)}");
				}

				if (validation.InvalidPaths.Count > 0)
				{
					problems.Add("The directory contains invalid file names.");
				}

				if (validation.NameCollisions.Count > 0)
				{
					problems.Add("The directory contains case-insensitive file-name collisions.");
				}

				throw new ResourceMissingException(
					$"The Civilization data directory is incomplete or invalid. {string.Join(" ", problems)}");
			}
			#endregion

			//ushort usInitialCS = 0x2045; // oEXE.InitialCS;
			ushort usInitialSS = 0x398d; // oEXE.InitialSS;
			ushort usInitialSP = 0x0800; // oEXE.InitialSP;

			this.oCPU.Memory.AllocateMemoryBlock(0xff00, 0x100, VCPUMemoryFlagsEnum.ReadWrite);
			this.oCPU.Memory.WriteUInt16(0xff00, 0x20cd);
			this.oCPU.Memory.WriteUInt16(0xff02, (ushort)(this.oCPU.Memory.FreeMemory.End >> 4));
			this.oCPU.Memory.WriteUInt8(0xff81, (byte)'\r');
			this.oCPU.Memory.MemoryRegions[1].AccessFlags = VCPUMemoryFlagsEnum.ReadWrite | VCPUMemoryFlagsEnum.WriteWarning | VCPUMemoryFlagsEnum.ReadWarning;

			uint uiEXEStart = VCPU.ToLinearAddress(usStartSegment, 0);
			uint uiEXELength = 0x3a0e0;

			byte[] resources = CommonResources.BinaryResources;

			this.oCPU.Memory.AllocateMemoryBlock(uiEXEStart, uiEXELength, VCPUMemoryFlagsEnum.ReadWrite);
			this.oCPU.Memory.WriteBlock(VCPU.ToLinearAddress(0x35cf, 0), resources, 0, resources.Length);
			this.oCPU.Memory.MemoryRegions[2].AccessFlags |= VCPUMemoryFlagsEnum.WriteWarning;

			// Define data and stack region
			uint uiDataStart = uiEXEStart + VCPU.ToLinearAddress(0x25cf, 0);
			uint uiDataEnd = uiEXEStart + VCPU.ToLinearAddress(0x2b01, 0xf0c0);

			this.oCPU.Memory.MemoryRegions[2].End = uiDataStart - 1;
			this.oCPU.Memory.MemoryRegions.Add(
				new VCPUMemoryRegion(uiDataStart, (uiDataEnd - uiDataStart) + 1, VCPUMemoryFlagsEnum.ReadWrite));

			// Initialize CPU
			//this.oCPU.CS.Word = (ushort)(usInitialCS + usStartSegment);
			this.oCPU.SS.UInt16 = (ushort)(usInitialSS + usStartSegment);
			this.oCPU.DS.UInt16 = (ushort)(usStartSegment - 0x10);
			this.oCPU.ES.UInt16 = (ushort)(usStartSegment - 0x10);
			this.oCPU.SP.UInt16 = usInitialSP;

			ushort usDataSegment = 0x3b01;

			// function body
			this.oCPU.PUSH_UInt16(this.oCPU.DS.UInt16);

			this.oCPU.DS.UInt16 = 0x3b01;

			// Not important, but just for case it's still needed, to be removed later
			string sPath =
				this.runtimeOptions.GetResourceFilePath("CIV.EXE");

			this.oCPU.WriteUInt8(this.oCPU.DS.UInt16, 0x61ee, (byte)'C');
			this.oCPU.WriteString(VCPU.ToLinearAddress(this.oCPU.DS.UInt16, 0x6156), sPath, sPath.Length);

			this.oCPU.DS.UInt16 = this.oCPU.POP_UInt16();
			this.oCPU.ES.UInt16 = this.oCPU.DS.UInt16;

			this.oCPU.SI.UInt16 = (ushort)(this.oCPU.Memory.FreeMemory.End >> 4); // top of memory
			this.oCPU.SI.UInt16 = this.oCPU.SUB_UInt16(this.oCPU.SI.UInt16, usDataSegment);

			// Init SS:SP
			this.oCPU.CLI();
			this.oCPU.SS.UInt16 = usDataSegment;
			this.oCPU.SP.UInt16 = this.oCPU.ADD_UInt16(this.oCPU.SP.UInt16, 0xe8c0);
			this.oCPU.STI();

			// Align SP
			this.oCPU.SP.UInt16 = this.oCPU.AND_UInt16(this.oCPU.SP.UInt16, 0xfffe);

			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, 0x5890, this.oCPU.SP.UInt16);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, 0x588c, this.oCPU.SP.UInt16);

			this.oCPU.AX.UInt16 = this.oCPU.SI.UInt16;
			this.oCPU.AX.UInt16 = this.oCPU.SHL_UInt16(this.oCPU.AX.UInt16, 4);
			this.oCPU.AX.UInt16 = this.oCPU.DEC_UInt16(this.oCPU.AX.UInt16);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, 0x588a, this.oCPU.AX.UInt16);

			this.oCPU.SI.UInt16 = this.oCPU.ADD_UInt16(this.oCPU.SI.UInt16, usDataSegment);
			this.oCPU.BX.UInt16 = this.oCPU.ES.UInt16;
			this.oCPU.BX.UInt16 = this.oCPU.SUB_UInt16(this.oCPU.BX.UInt16, this.oCPU.SI.UInt16);
			this.oCPU.BX.UInt16 = this.oCPU.NEG_UInt16(this.oCPU.BX.UInt16);
			if (this.oCPU.Memory.ResizeMemoryBlock(this.oCPU.ES.UInt16, this.oCPU.BX.UInt16))
			{
				this.oCPU.Flags.C = false;
				this.oCPU.AX.UInt16 = 0;
			}
			else
			{
				this.oCPU.Flags.C = true;
				this.oCPU.AX.UInt16 = 8;
				this.oCPU.BX.UInt16 = 0;
			}

			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, 0x5901, this.oCPU.DS.UInt16);

			this.oCPU.ES.UInt16 = this.oCPU.SS.UInt16;
			this.oCPU.DS.UInt16 = this.oCPU.SS.UInt16;

			// Clear the rest of data and stack segment 0x652e - 0xe8c0
			for (int i = 0x652e; i < this.oCPU.SP.UInt16; i++)
			{
				if (i < 0x70ec && i > 0x70ec + 0xdff)
					this.oCPU.WriteUInt8(usDataSegment, (ushort)i, 0);
			}

			// DOS version
			this.oCPU.WriteUInt16(this.oCPU.DS.UInt16, 0x5903, 0x616);

			// Environment block is not used
			// Argument block is not used
			this.oCPU.WriteUInt16(this.oCPU.DS.UInt16, 0x5922, 0);
			this.oCPU.WriteUInt16(this.oCPU.DS.UInt16, 0x5920, 0);
			this.oCPU.WriteUInt16(this.oCPU.DS.UInt16, 0x591e, 0);

			this.oCPU.BP.UInt16 = 0x0;

			// Call our StartGame function
			this.StartGame.F0_11a8_0008_StartGame();

			this.CAPI.exit(0);
		}

		public void RequestStop()
		{
			this.CPU.OnApplicationExit();
		}

		public MouseEvent PeekMouseEvent()
		{
			this.oCPU.DoEvents();

			lock (OpenCivOneGame.KeyboardAndMouseLock)
			{
				if (this.mouseEvents.Count > 0)
				{
					MouseEvent mouseEvent = this.mouseEvents[0];

					// We can safely remove mouse movement event
					if (mouseEvent.Buttons == MouseButtonsEnum.None)
					{
						this.mouseEvents.RemoveAt(0);
						this.lastMouseEvent = mouseEvent;
					}
					
					return mouseEvent;
				}

				return this.lastMouseEvent;
			}
		}

		public bool HasNewMouseEvent()
		{
			this.oCPU.DoEvents();

			lock (OpenCivOneGame.KeyboardAndMouseLock)
			{
				if (this.mouseEvents.Count > 0)
				{
					return true;
				}

				return false;
			}
		}

		public MouseEvent GetMouseEvent()
		{
			this.oCPU.DoEvents();

			lock (OpenCivOneGame.KeyboardAndMouseLock)
			{
				if (this.mouseEvents.Count > 0)
				{
					MouseEvent mouseEvent = this.mouseEvents[0];
					this.mouseEvents.RemoveAt(0);
					this.lastMouseEvent = mouseEvent;

					return mouseEvent;
				}

				return this.lastMouseEvent;
			}
		}

		/// <summary>
		/// Clears the mouse buffer and ensures no mouse button is pressed
		/// </summary>
		public void ClearMouseEventsAndEnsureNoMouseButtonIsPressed()
		{
			lock (OpenCivOneGame.KeyboardAndMouseLock)
			{
				if (this.mouseEvents.Count > 0)
				{
					this.lastMouseEvent = this.mouseEvents[this.mouseEvents.Count - 1];
				}

				this.mouseEvents.Clear();
			}

			while (this.GetMouseEvent().Buttons != MouseButtonsEnum.None) { Thread.Sleep(1); }
		}

		public IClassicGameHost Host { get => this.host; }

		public VCPU CPU { get => this.oCPU; }

		public GameData GameData { get => this.gameData; }

		public ClassicUnitAutomationState UnitAutomationState =>
			this.unitAutomationState;

		public ClassicRuntimePresentationState PresentationState =>
			this.presentationState;

		public string ResourcePath { get => this.gameResourcePath; }

		public string MainPath { get => this.gameMainPath; }

		public string SavePath { get => this.gameSavePath; }

		public ClassicRuntimeOptions RuntimeOptions { get => this.runtimeOptions; }

		/// <summary>
		/// Stops the old turn immediately after a successful in-game load so
		/// no post-load state is processed by the turn that opened the dialog.
		/// </summary>
		public bool RestartTurnAfterInGameLoad { get; set; }

		public ClassicRuntimeFileResolver RuntimeFiles { get => this.runtimeFiles; }

		public Queue<int> Keys
		{
			get { return this.keys; }
		}

		internal void ObserveConsumedKeyForAutomaticEndTurnPause(int key)
		{
			if (key != 0x1b ||
				Volatile.Read(
					ref this.automaticEndTurnPauseCaptureEnabled) == 0 ||
				!ClassicAiRuntimeProfiles.UsesSmartEnhancements(
					this.GameData.AiProfile) ||
				this.GameData.GameSettingFlags.EndOfTurn ||
				this.PresentationState.Capture().IsEndOfTurnPrompt)
			{
				return;
			}

			// A warning or report may consume Escape before PlayerTurn regains
			// control. Preserve that intent as a transient, one-shot request so
			// automatic turn advance can still stop at the next safe boundary.
			Interlocked.Exchange(
				ref this.automaticEndTurnPauseRequested,
				1);
		}

		internal void BeginHumanInputPhaseForAutomaticEndTurnPause()
		{
			Interlocked.Exchange(
				ref this.automaticEndTurnPauseCaptureEnabled,
				0);
		}

		internal void BeginAutomaticAdvancePhaseForEndTurnPause()
		{
			int enabled =
				ClassicAiRuntimeProfiles.UsesSmartEnhancements(
					this.GameData.AiProfile) &&
				!this.GameData.GameSettingFlags.EndOfTurn
					? 1
					: 0;
			Interlocked.Exchange(
				ref this.automaticEndTurnPauseCaptureEnabled,
				enabled);
		}

		internal bool ConsumeAutomaticEndTurnPauseRequest() =>
			Interlocked.Exchange(
				ref this.automaticEndTurnPauseRequested,
				0) != 0;

		public List<MouseEvent> MouseEvents
		{
			get { return this.mouseEvents; }
		}

		#region Logs
		public LogWrapper Log
		{
			get { return this.oLog; }
		}

		public LogWrapper InterruptLog
		{
			get { return this.oInterruptLog; }
		}

		public LogWrapper GoToLog
		{
			get { return this.oGoToLog; }
		}

		public static void LogUnit(OpenCivOneGame game, LogWrapper log, int playerID, int unitID, int humanPlayerID)
		{
			if (playerID >= game.GameData.Players.Length || unitID >= game.GameData.Players[playerID].Units.Length)
			{
				log.WriteLine($"// Illegal indexes, PlayerID: {playerID}{((playerID == humanPlayerID) ? " (Human player)" : "")}, UnitID: {unitID}");
			}
			else
			{
				Unit unit = game.GameData.Players[playerID].Units[unitID];

				log.WriteLine($"// Player[{playerID}{((playerID == humanPlayerID) ? " (Human player)" : "")}].Unit[{unitID}] = {{TypeID: {unit.UnitType}, Status: {unit.Status}, Position: {unit.Position}, GoTo: {unit.GoToDestination}}}");
			}
		}
		#endregion

		#region Public Segment getters
		public StartGame StartGame
		{
			get { return this.startGame; }
		}

		public CommonTools CommonTools
		{
			get { return this.commonTools; }
		}

		public Segment_1238 Segment_1238
		{
			get { return this.oSegment_1238; }
		}

		public MenuBoxDialog MenuBoxDialog
		{
			get { return this.menuBoxDialog; }
		}

		public PlayerTurn PlayerTurn
		{
			get { return this.playerTurn; }
		}

		public Tools Tools
		{
			get { return this.tools; }
		}

		public DrawTools DrawTools
		{
			get { return this.drawTools; }
		}

		public ImageTools ImageTools
		{
			get { return this.imageTools; }
		}

		public LanguageTools LanguageTools
		{
			get { return this.languageTools; }
		}

		public MapManagement MapManagement
		{
			get { return this.mapManagement; }
		}

		public UnitManagement UnitManagement
		{
			get { return this.unitManagement; }
		}

		public UnitGoTo UnitGoTo
		{
			get { return this.unitGoTo; }
		}

		public Actions Segment_2459
		{
			get { return this.oSegment_2459; }
		}

		public AIEngine AIEngine
		{
			get { return this.aiEngine; }
		}

		public Segment_1ade Segment_1ade
		{
			get { return this.oSegment_1ade; }
		}

		public CityWorker CityWorker
		{
			get { return this.cityWorker; }
		}

		public AttackActions Segment_29f3
		{
			get { return this.oSegment_29f3; }
		}

		public Segment_2517 Segment_2517
		{
			get { return this.oSegment_2517; }
		}

		public Menus Menus
		{
			get { return this.menus; }
		}

		public MainIntro MainIntro
		{
			get { return this.mainIntro; }
		}

		public MeetWithKing MeetWithKing
		{
			get { return this.meetWithKing; }
		}

		public MapInitAndIntro MapInitAndIntro
		{
			get { return this.mapInitAndIntro; }
		}

		public Help Help
		{
			get { return this.help; }
		}

		public LoadAndSave LoadAndSave
		{
			get { return this.loadAndSave; }
		}

		public HallOfFame HallOfFame
		{
			get { return this.hallOfFame; }
		}

		public StartGameMenu StartGameMenu
		{
			get { return this.startGameMenu; }
		}

		public TextBoxDialogs TextBoxDialogs
		{
			get { return this.textBoxDialogs; }
		}

		public Overlay_14 Overlay_14
		{
			get { return this.oOverlay_14; }
		}

		public Encyclopedia Encyclopedia
		{
			get { return this.encyclopedia; }
		}

		public News News
		{
			get { return this.news; }
		}

		public CityView CityView
		{
			get { return this.cityView; }
		}

		public Overlay_18 Overlay_18
		{
			get { return this.oOverlay_18; }
		}

		public Overlay_22 Overlay_22
		{
			get { return this.oOverlay_22; }
		}

		public Replay Replay
		{
			get { return this.replay; }
		}

		public Reports Reports
		{
			get { return this.reports; }
		}

		public Overlay_20 Overlay_20
		{
			get { return this.oOverlay_20; }
		}

		public Palace Palace
		{
			get { return this.palace; }
		}

		public ShowDebugDetails ShowDebugDetails
		{
			get { return this.showDebugDetails; }
		}

		public Secession Secession
		{
			get { return this.secession; }
		}

		public CAPI CAPI
		{
			get { return this.CApi; }
		}

		public GDriver Graphics
		{
			get { return this.graphics; }
		}

		public NSound Sound
		{
			get { return this.sound; }
		}
		#endregion
	}
}
