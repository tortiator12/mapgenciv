using OpenCivOne.Graphics;
using OpenCivOne.Localization;
using OpenCivOne.Platform;
using OpenCivOne.Runtime;
using System.Text;

namespace OpenCivOne
{
	public class LoadAndSave
	{
		private static readonly ClassicSaveMetadataSerializer
			SaveMetadataSerializer = new();

		private OpenCivOneGame parent;
		private readonly ClassicSavePairFiles savePairFiles;

		private bool loadingGame = false;
		private int gameIndex = 0;

		public LoadAndSave(OpenCivOneGame parent)
		{
			this.parent = parent;
			this.savePairFiles = new ClassicSavePairFiles(parent.RuntimeOptions);
		}

		/// <summary>
		/// ?
		/// </summary>
		/// <returns></returns>
		public int F11_0000_0000_LoadGameDialog()
		{
			//this.oCPU.Log.EnterBlock($"F11_0000_0000({flag})");

			// function body

			/*LoadGameDialog? dialog = null;
			bool creatingWindow = true;

			Dispatcher.UIThread.Invoke(() => { try { dialog = new LoadGameDialog(this.parent); dialog.ShowDialog(this.parent.MainWindow); } finally { creatingWindow = false; } });

			while (creatingWindow) { Thread.Sleep(1); }

			while (dialog != null && !dialog.IsClosed) { Thread.Sleep(1); }//*/

			this.parent.DrawTools.FillRectangle(this.parent.Var_aa_Screen0_Rectangle, 0, 0, 320, 200, 15);

			if (!ClassicAiRuntimeProfiles.UsesSmartEnhancements(
					this.parent.GameData.AiProfile))
			{
				return LoadOriginalGameDialog();
			}

			return LoadSaveCatalogDialog();
		}

		/// <summary>
		/// The start screen has no active rules profile yet. It must therefore
		/// show every compatible save bundle instead of guessing Original 1991
		/// and hiding named 1991+ saves.
		/// </summary>
		public int LoadGameFromMainMenuDialog()
		{
			this.parent.DrawTools.FillRectangle(
				this.parent.Var_aa_Screen0_Rectangle,
				0,
				0,
				320,
				200,
				15);
			return LoadSaveCatalogDialog();
		}

		private int LoadSaveCatalogDialog()
		{
			IReadOnlyList<ClassicSaveCatalogEntry> catalog =
				BuildSaveCatalog();
			int pageIndex = 0;

			while (true)
			{
				// ShowMenuBox draws directly into screen 0 and intentionally
				// leaves the selected page behind. A paged 1991+ catalog must
				// therefore restore its plain background before drawing the
				// next page.
				this.parent.DrawTools.FillRectangle(
					this.parent.Var_aa_Screen0_Rectangle,
					0,
					0,
					320,
					200,
					15);
				ClassicSaveCatalogPagePlan page =
					ClassicSaveCatalogPagePlan.Create(
						catalog,
						pageIndex);

				this.parent.Var_b276_MenuBoxDisabledOptions =
					page.DisabledOptionsMask;
				this.parent.Var_2f9a_MenuBoxDefaultOptionIndex =
					page.DefaultOptionIndex;
				int selectedOption;
				try
				{
					selectedOption =
						this.parent.MenuBoxDialog
							.F0_2d05_0031_ShowMenuBox(
								page.Text,
								32,
								33,
								false,
								false,
								true);
				}
				finally
				{
					this.parent.Var_b276_MenuBoxDisabledOptions = 0;
					this.parent.Var_2f9a_MenuBoxDefaultOptionIndex = -1;
				}

				if (selectedOption < 0 ||
					selectedOption >= page.Options.Count)
				{
					this.gameIndex = -1;
					return this.gameIndex;
				}

				ClassicSaveCatalogOption selected =
					page.Options[selectedOption];
				if (selected.Kind ==
					ClassicSaveCatalogOptionKind.PreviousPage)
				{
					pageIndex--;
					continue;
				}

				if (selected.Kind ==
					ClassicSaveCatalogOptionKind.NextPage)
				{
					pageIndex++;
					continue;
				}

				if (selected.Kind !=
						ClassicSaveCatalogOptionKind.Save ||
					selected.FileName is null)
				{
					continue;
				}

				this.gameIndex =
					GetClassicSlotIndex(selected.FileName);
				if (!F11_0000_0103_LoadGame(
						selected.FileName,
						this.gameIndex))
				{
					this.gameIndex = -1;
				}

				return this.gameIndex;
			}
		}

		private int LoadOriginalGameDialog()
		{
			List<ClassicSaveSlotInfo> slots = new();
			for (int slotIndex = 0; slotIndex < 10; slotIndex++)
			{
				slots.Add(
					InspectSaveSlot($"CIVIL{slotIndex}.SVE"));
			}

			ClassicSaveSlotMenuPlan menuPlan =
				ClassicSaveSlotMenuPlan.Create(
					slots,
					ClassicSaveDialogPurpose.Load);
			this.parent.Var_b276_MenuBoxDisabledOptions =
				menuPlan.DisabledOptionsMask;
			this.parent.Var_2f9a_MenuBoxDefaultOptionIndex =
				menuPlan.DefaultOptionIndex;
			try
			{
				this.gameIndex =
					this.parent.MenuBoxDialog
						.F0_2d05_0031_ShowMenuBox(
							menuPlan.Text,
							48,
							65,
							false,
							false,
							true);
			}
			finally
			{
				this.parent.Var_b276_MenuBoxDisabledOptions = 0;
				this.parent.Var_2f9a_MenuBoxDefaultOptionIndex = -1;
			}

			if (this.gameIndex < 0 ||
				this.gameIndex >= slots.Count ||
				!slots[this.gameIndex].CanLoad)
			{
				this.gameIndex = -1;
				return this.gameIndex;
			}

			if (!F11_0000_0103_LoadGame(
					$"CIVIL{this.gameIndex}.SVE",
					this.gameIndex))
			{
				this.gameIndex = -1;
			}

			return this.gameIndex;
		}

		public IReadOnlyList<ClassicSaveCatalogEntry> BuildSaveCatalog()
		{
			HashSet<string> fileNames =
				new(StringComparer.OrdinalIgnoreCase);

			if (Directory.Exists(this.parent.RuntimeOptions.SavePath))
			{
				foreach (string pattern in
					new[]
					{
						"*.SVE",
						"*.MAP",
						"*.P91",
					})
				{
					foreach (string path in Directory.EnumerateFiles(
						this.parent.RuntimeOptions.SavePath,
						pattern,
						SearchOption.TopDirectoryOnly))
					{
						string slotName =
							Path.GetFileNameWithoutExtension(path);
						if (!string.IsNullOrWhiteSpace(slotName))
						{
							fileNames.Add($"{slotName}.SVE");
						}
					}
				}
			}

			// Owner-data installations may still contain the ten original
			// DOS slots outside the mutable save directory.
			for (int slotIndex = 0; slotIndex < 10; slotIndex++)
			{
				string fileName = $"CIVIL{slotIndex}.SVE";
				if (InspectSaveSlot(fileName).CanLoad)
				{
					fileNames.Add(fileName);
				}
			}

			List<ClassicSaveCatalogEntry> entries = new();
			foreach (string fileName in fileNames)
			{
				ClassicSaveSlotInfo inspected =
					InspectSaveSlot(fileName);
				DateTime lastWriteTimeUtc =
					GetSaveArtifactLastWriteTimeUtc(fileName);
				ClassicSaveSlotInfo displayed =
					inspected with
					{
						DisplayText =
							BuildCatalogDisplayText(
								fileName,
								inspected,
								lastWriteTimeUtc),
					};
				entries.Add(
					new ClassicSaveCatalogEntry(
						fileName.ToUpperInvariant(),
						displayed,
						lastWriteTimeUtc,
						IsAutoSaveFileName(fileName)));
			}

			return entries
				.OrderByDescending(entry => entry.LastWriteTimeUtc)
				.ThenBy(entry => entry.FileName, StringComparer.OrdinalIgnoreCase)
				.ToArray();
		}

		/// <summary>
		/// Reads an information from a saved game
		/// </summary>
		/// <param name="filename"></param>
		/// <param name="success"></param>
		/// <returns>True if command succeeded</returns>
		public string F11_0000_0103_ReadGameInfo(string filename, out bool success)
		{
			ClassicSaveSlotInfo slot = InspectSaveSlot(filename);
			success = slot.CanLoad;
			return slot.DisplayText;
		}

		public ClassicSaveSlotInfo InspectSaveSlot(string filename)
		{
			try
			{
				return this.savePairFiles.InspectBundle(
					filename,
					inspection =>
						inspection.Presence switch
						{
							ClassicSaveBundlePresence.Empty =>
								CreateUnavailableSlot(
									ClassicSaveSlotStatus.Empty,
									ClassicGameTextKey.SaveSlotEmpty),
							ClassicSaveBundlePresence.Incomplete =>
								CreateUnavailableSlot(
									ClassicSaveSlotStatus.Invalid,
									ClassicGameTextKey.SaveSlotInvalid),
							_ => InspectSaveBundle(
								inspection.Bundle),
						});
			}
			catch
			{
				return CreateUnavailableSlot(
					ClassicSaveSlotStatus.Invalid,
					ClassicGameTextKey.SaveSlotInvalid);
			}
		}

		private ClassicSaveSlotInfo InspectSaveBundle(
			ClassicSaveBundlePaths bundle)
		{
			try
			{
				ValidatedSaveBundle validatedBundle =
					ReadAndValidateBundle(bundle);
				string gameInformation =
					ReadGameInformation(
						validatedBundle.StateBytes);
				ClassicAiProfile displayProfile =
					GetStoredBundleProfile(validatedBundle);
				ClassicGameTextKey prefixKey =
					validatedBundle.HasMetadata
						? displayProfile ==
								ClassicAiProfile.Smart1991Plus
							? ClassicGameTextKey
								.SaveSlotEnhancedPrefix
							: ClassicGameTextKey
								.SaveSlotClassicPrefix
						: ClassicGameTextKey
							.SaveSlotLegacyPrefix;
				ClassicSaveSlotStatus status =
					validatedBundle.HasMetadata
						? ClassicSaveSlotStatus
							.ClassicCompatible
						: ClassicSaveSlotStatus
							.LegacyCompatible;

				return new ClassicSaveSlotInfo(
					status,
					ClassicGameText.Current[prefixKey] +
						gameInformation +
						"\n");
			}
			catch (SaveProfileUnavailableException)
			{
				return CreateUnavailableSlot(
					ClassicSaveSlotStatus.ProfileUnavailable,
					ClassicGameTextKey
						.SaveSlotProfileUnavailable);
			}
			catch
			{
				return CreateUnavailableSlot(
					ClassicSaveSlotStatus.Invalid,
					ClassicGameTextKey.SaveSlotInvalid);
			}
		}

		private static ClassicSaveSlotInfo CreateUnavailableSlot(
			ClassicSaveSlotStatus status,
			ClassicGameTextKey textKey) =>
			new(status, ClassicGameText.Current[textKey]);

		private string ReadGameInformation(byte[] stateBytes)
		{
			using MemoryStream reader = new(
				stateBytes,
				writable: false);

			reader.Seek(2, SeekOrigin.Begin);
			int humanPlayerID = ReadInt16(reader);

			reader.Seek(8, SeekOrigin.Begin);
			int currentYear = ReadInt16(reader);

			reader.Seek(10, SeekOrigin.Begin);
			int gameDifficulty = ReadInt16(reader);

			reader.Seek(
				16 + (humanPlayerID * 14),
				SeekOrigin.Begin);
			string humanPlayerName = ReadString(reader, 14);

			reader.Seek(
				128 + (humanPlayerID * 12),
				SeekOrigin.Begin);
			string humanNationName = ReadString(reader, 12);

			string difficultyName =
				ClassicGameText.Current[
					GetDifficultyTextKey(gameDifficulty)];
			string yearText =
				ClassicGameText.Current.Format(
					currentYear < 0
						? ClassicGameTextKey
							.ReportYearBeforeCommonEra
						: ClassicGameTextKey
							.ReportYearCommonEra,
					Math.Abs(currentYear));

			return
				$"{difficultyName} {humanPlayerName}, {humanNationName}/{yearText}";
		}

		private static ClassicGameTextKey GetDifficultyTextKey(
			int difficultyLevel) =>
			difficultyLevel switch
			{
				0 => ClassicGameTextKey.DifficultyNameChieftain,
				1 => ClassicGameTextKey.DifficultyNameWarlord,
				2 => ClassicGameTextKey.DifficultyNamePrince,
				3 => ClassicGameTextKey.DifficultyNameKing,
				4 => ClassicGameTextKey.DifficultyNameEmperor,
				_ => throw new InvalidDataException(
					"Classic save difficulty is outside the supported range."),
			};

		/// <summary>
		/// Loads a data from a save game
		/// </summary>
		/// <param name="filename"></param>
		/// <returns>True if command succeeded</returns>
		public bool F11_0000_0103_LoadGame(string filename, int gameIndex)
		{
			//this.oCPU.Log.EnterBlock($"F11_0000_0103_LoadGame(0x{filename:x4}, {flag})");

			// function body
			if (!F11_0000_083b_LoadGameData(filename))
			{
				return false;
			}

			//this.oParent.GameInitAndIntro.F7_0000_1440_ConstructWaterPath();

			if (gameIndex < 4)
			{
				this.parent.Var_df60 = 1;
			}
			else
			{
				this.parent.Var_df60 = 2;
			}

			this.parent.Var_3484 = -3;
			this.parent.GameData.SpaceshipFlags &= 0x7ffe;

			return true;
		}

		/// <summary>
		/// ?
		/// </summary>
		/// <param name="autoSave"></param>
		public void F11_0000_036a_SaveGameDialog(bool autoSave)
		{
			//this.CPU.Log.EnterBlock($"F11_0000_036a({autoSave})");

			// function body
			this.loadingGame = false;

			if (autoSave)
			{
				// Auto saves happen at a turn boundary and must not depend on
				// whichever screen, font, or advisor style the preceding game
				// event left active.
				this.gameIndex =
					4 + (((this.parent.GameData.TurnCount / 50) - 1) % 6);
				SaveGameData(
					$"CIVIL{this.gameIndex}.SVE",
					showFailureDialog: false);
				return;
			}

			this.parent.DrawTools.FillRectangle(this.parent.Var_aa_Screen0_Rectangle, 0, 0, 320, 200, 15);

			if (ClassicAiRuntimeProfiles.UsesSmartEnhancements(
					this.parent.GameData.AiProfile))
			{
				SaveNamed1991PlusGame();
				this.parent.Graphics.F0_VGA_07d8_DrawImage(
					this.parent.Var_19d4_Screen1_Rectangle,
					0,
					0,
					320,
					200,
					this.parent.Var_aa_Screen0_Rectangle,
					0,
					0);
				return;
			}

			// Instruction address 0x0000:0x03d3, size: 5
			this.parent.Var_2f9a_MenuBoxDefaultOptionIndex = this.parent.Tools.F0_2dc4_007c_CheckValueRange(this.gameIndex, 0, 3);

			if (!autoSave)
			{
				List<ClassicSaveSlotInfo> slots = new();

				for (int i = 0; i < 4; i++)
				{
					slots.Add(
						InspectSaveSlot($"CIVIL{i}.SVE"));
				}

				ClassicSaveSlotMenuPlan menuPlan =
					ClassicSaveSlotMenuPlan.Create(
						slots,
						ClassicSaveDialogPurpose.Save,
						this.parent
							.Var_2f9a_MenuBoxDefaultOptionIndex);

				// Instruction address 0x0000:0x03f5, size: 5
				this.parent.Var_b276_MenuBoxDisabledOptions =
					menuPlan.DisabledOptionsMask;
				this.parent.Var_2f9a_MenuBoxDefaultOptionIndex =
					menuPlan.DefaultOptionIndex;
				try
				{
					this.gameIndex =
						this.parent.MenuBoxDialog
							.F0_2d05_0031_ShowMenuBox(
								menuPlan.Text,
								48,
								33,
								false,
								false,
								true);
				}
				finally
				{
					this.parent.Var_b276_MenuBoxDisabledOptions =
						0;
					this.parent
						.Var_2f9a_MenuBoxDefaultOptionIndex =
							-1;
				}
			}
			if (this.gameIndex != -1)
			{
				this.parent.Var_db38 = 1;

				StringBuilder saveGameText = new();

				saveGameText.Append($" CIVIL{this.gameIndex}.SVE\n {this.parent.Array_33a2_GameDifficultyNames[this.parent.GameData.DifficultyLevel]} ");
				saveGameText.Append($"{this.parent.GameData.Players[this.parent.GameData.HumanPlayerID].Name}\n {this.parent.GameData.Players[this.parent.GameData.HumanPlayerID].Nation}");
				saveGameText.Append($"/{Math.Abs(this.parent.GameData.Year)} {((this.parent.GameData.Year < 0) ? "BC\n" : "AD\n")}");
				saveGameText.Append("\n ... save in progress.\n");

				// Instruction address 0x0000:0x05c3, size: 5
				this.parent.MenuBoxDialog.F0_2d05_0031_ShowMenuBox(saveGameText.ToString(), 64, 86, true, false, true);

				bool saveSucceeded =
					F11_0000_08f6_SaveGameData($"CIVIL{this.gameIndex}.SVE");

				if (!autoSave)
				{
					string resultText = saveSucceeded
						? ClassicGameText.Current[ClassicGameTextKey.GameSaved]
						: ClassicGameText.Current[ClassicGameTextKey.GameNotSaved];
					this.parent.DrawTools.F0_1182_00b3_DrawCenteredStringToScreen0(
						resultText,
						125,
						132,
						0);
					this.parent.DrawTools.F0_1182_00b3_DrawCenteredStringToScreen0(
						ClassicGameText.Current[ClassicGameTextKey.ContinueAfterSave],
						125,
						142,
						0);
					this.parent.Segment_2459
						.F0_2459_0918_WaitForKeyPressOrMouseClick();
				}
			}

			this.parent.Graphics.F0_VGA_07d8_DrawImage(this.parent.Var_19d4_Screen1_Rectangle, 0, 0, 320, 200, this.parent.Var_aa_Screen0_Rectangle, 0, 0);
		}

		private void SaveNamed1991PlusGame()
		{
			string defaultName =
				BuildDefault1991PlusSaveName();
			string? requestedName =
				this.parent.Host.ShowTextInput(
					ClassicGameText.Current[
						ClassicGameTextKey.SaveGameNameDialogTitle],
					ClassicGameText.Current[
						ClassicGameTextKey.SaveGameNameDialogPlaceholder],
					defaultName,
					maxTextLength: 24,
					allowEmptyText: false);
			if (requestedName is null)
			{
				return;
			}

			string? safeName = Normalize1991PlusSaveName(requestedName);
			if (safeName is null)
			{
				this.parent.Host.ShowInformation(
					ClassicGameText.Current[
						ClassicGameTextKey.SaveGameNameInvalid],
					ClassicGameText.Current[
						ClassicGameTextKey.SaveGameNameDialogTitle]);
				return;
			}

			string fileName = $"P91-{safeName}.SVE";
			bool saveAlreadyExists =
				this.savePairFiles.InspectBundle(
					fileName,
					inspection =>
						inspection.Presence !=
						ClassicSaveBundlePresence.Empty);
			if (saveAlreadyExists &&
				!this.parent.Host.ShowConfirmation(
					ClassicGameText.Current[
						ClassicGameTextKey
							.SaveGameOverwriteQuestion],
					ClassicGameText.Current[
						ClassicGameTextKey
							.SaveGameNameDialogTitle]))
			{
				return;
			}

			this.gameIndex = 0;
			this.parent.Var_db38 = 1;
			bool saveSucceeded =
				F11_0000_08f6_SaveGameData(fileName);
			this.parent.Host.ShowInformation(
				ClassicGameText.Current[
					saveSucceeded
						? ClassicGameTextKey.GameSaved
						: ClassicGameTextKey.GameNotSaved],
				ClassicGameText.Current[
					ClassicGameTextKey.SaveGameNameDialogTitle]);
		}

		private string BuildDefault1991PlusSaveName()
		{
			Player humanPlayer =
				this.parent.GameData.Players[
					this.parent.GameData.HumanPlayerID];
			string era =
				this.parent.GameData.Year < 0
					? "BC"
					: "AD";
			return
				$"{humanPlayer.Name}-{Math.Abs(this.parent.GameData.Year)}{era}";
		}

		private static string? Normalize1991PlusSaveName(
			string requestedName)
		{
			StringBuilder safeName = new();
			bool separatorPending = false;

			foreach (char character in requestedName.Trim())
			{
				char normalizedCharacter =
					char.ToUpperInvariant(character) switch
					{
						'Ä' => 'A',
						'Ö' => 'O',
						'Ü' => 'U',
						'ß' => 'S',
						_ => char.ToUpperInvariant(character),
					};

				if (normalizedCharacter is >= 'A' and <= 'Z' or
					>= '0' and <= '9')
				{
					if (separatorPending && safeName.Length > 0)
					{
						safeName.Append('-');
					}
					safeName.Append(normalizedCharacter);
					separatorPending = false;
				}
				else if (character is ' ' or '-' or '_')
				{
					separatorPending = true;
				}
			}

			return safeName.Length == 0
				? null
				: safeName.ToString();
		}

		private string BuildCatalogDisplayText(
			string fileName,
			ClassicSaveSlotInfo slot,
			DateTime lastWriteTimeUtc)
		{
			string slotName =
				Path.GetFileNameWithoutExtension(fileName);
			string displayName =
				slotName.StartsWith(
					"P91-",
					StringComparison.OrdinalIgnoreCase)
					? slotName[4..].Replace('-', ' ')
					: slotName;
			if (displayName.Length > 10)
			{
				displayName = displayName[..10];
			}

			string dateText =
				lastWriteTimeUtc == DateTime.MinValue
					? "--.--.--"
					: lastWriteTimeUtc
						.ToLocalTime()
						.ToString(
							"dd.MM.yy",
							System.Globalization.CultureInfo
								.InvariantCulture);
			string slotText = slot.DisplayText.Trim();
			int prefixEnd = slotText.IndexOf(']');
			int yearSeparator = slotText.LastIndexOf('/');
			if (slot.CanLoad &&
				prefixEnd >= 0 &&
				yearSeparator > prefixEnd)
			{
				return
					$" {dateText} {displayName} " +
					$"{slotText[..(prefixEnd + 1)]} " +
					$"{slotText[(yearSeparator + 1)..]}\n";
			}

			return $" {dateText} {displayName}: {slotText}\n";
		}

		private DateTime GetSaveArtifactLastWriteTimeUtc(
			string fileName)
		{
			string slotName =
				Path.GetFileNameWithoutExtension(fileName);
			DateTime latest = DateTime.MinValue;
			foreach (string extension in
				new[] { "SVE", "MAP", "P91" })
			{
				string path =
					this.parent.RuntimeOptions.GetSaveFilePath(
						$"{slotName}.{extension}");
				if (File.Exists(path))
				{
					DateTime written =
						File.GetLastWriteTimeUtc(path);
					if (written > latest)
					{
						latest = written;
					}
				}
			}

			return latest;
		}

		private static bool IsAutoSaveFileName(string fileName)
		{
			string slotName =
				Path.GetFileNameWithoutExtension(fileName);
			return slotName.Length == 6 &&
				slotName.StartsWith(
					"CIVIL",
					StringComparison.OrdinalIgnoreCase) &&
				slotName[5] is >= '4' and <= '9';
		}

		private static int GetClassicSlotIndex(string fileName)
		{
			string slotName =
				Path.GetFileNameWithoutExtension(fileName);
			return slotName.Length == 6 &&
				slotName.StartsWith(
					"CIVIL",
					StringComparison.OrdinalIgnoreCase) &&
				slotName[5] is >= '0' and <= '9'
					? slotName[5] - '0'
					: 0;
		}

		/// <summary>
		/// ?
		/// </summary>
		/// <param name="filename"></param>
		/// <returns></returns>
		public bool F11_0000_083b_LoadGameData(string filename)
		{
			filename = filename.ToUpper();

			//this.CPU.Log.EnterBlock($"F11_0000_083b_LoadGameData('{path}')");

			// function body
			string filenameWithoutExtension = Path.GetFileNameWithoutExtension(CAPI.GetDOSFileName(filename));
			try
			{
				return this.savePairFiles.ReadBundle(
					filenameWithoutExtension,
					bundle => LoadGameDataFromBundle(
						bundle,
						filenameWithoutExtension));
			}
			catch (Exception ex)
			{
				TryWriteLoadFailureLog(
					filenameWithoutExtension,
					ex);
				return false;
			}
		}

		private bool LoadGameDataFromBundle(
			ClassicSaveBundlePaths bundle,
			string filenameWithoutExtension)
		{
			try
			{
				ValidatedSaveBundle validatedBundle =
					ReadAndValidateBundle(bundle);
				if (!LoadGameDataFromPayload(
					validatedBundle.StateBytes,
					validatedBundle.MapBytes,
					filenameWithoutExtension))
				{
					return false;
				}

				ClassicAiProfile effectiveProfile =
					ResolveLoadedProfile(validatedBundle);
				this.parent.GameData.AiProfile = effectiveProfile;
				if (ClassicAiRuntimeProfiles.UsesSmartEnhancements(
						effectiveProfile))
				{
					EnableSmartAutomationDefaultsForLegacyBundle(
						validatedBundle);
					EnableOptionsRequiredByOrders(
						validatedBundle.UnitAutomation);
					this.parent.UnitAutomationState.ReplaceFromSave(
						this.parent.GameData,
						validatedBundle.UnitAutomation);
				}
				else
				{
					this.parent.GameData.GameSettingFlags
						.Disable1991PlusOptions();
					this.parent.UnitAutomationState.Clear();
				}
				return true;
			}
			catch (Exception ex)
			{
				TryWriteLoadFailureLog(
					filenameWithoutExtension,
					ex);
				return false;
			}
		}

		private bool LoadGameDataFromPayload(
			byte[] stateBytes,
			byte[] mapBytes,
			string filenameWithoutExtension)
		{
			bool bSuccess = false;
			try
			{
				// read map file
				GBitmap? map;

				if ((map = GBitmap.FromPICBytes(
					mapBytes,
					true)) == null)
					throw new Exception($"Can't read Map file '{filenameWithoutExtension}.MAP'");

				this.parent.GameData.Map = map;

				if (this.parent.Graphics.Screens.ContainsKey(3))
				{
					this.parent.Graphics.Screens.RemoveByKey(3);
				}

				this.parent.Graphics.Screens.Add(3, this.parent.GameData.Map);

				// read sve file
				using MemoryStream reader = new(
					stateBytes,
					writable: false);
				this.parent.GameData.TurnCount = ReadInt16(reader);
				this.parent.GameData.HumanPlayerID = ReadInt16(reader);
				this.parent.GameData.PlayerFlags = ReadInt16(reader);
				this.parent.GameData.RandomSeed = ReadUInt16(reader);
				this.parent.GameData.Year = ReadInt16(reader);
				this.parent.GameData.DifficultyLevel = ReadInt16(reader);
				this.parent.GameData.ActiveCivilizations = ReadInt16(reader);
				this.parent.GameData.Players[this.parent.GameData.HumanPlayerID].ResearchTechnologyID = ReadInt16(reader);

				for (int i = 0; i < 8; i++)
				{
					this.parent.GameData.Players[i].Name = ReadString(reader, 14);
				}

				for (int i = 0; i < 8; i++)
				{
					this.parent.GameData.Players[i].Nation = ReadString(reader, 12);
				}

				for (int i = 0; i < 8; i++)
				{
					this.parent.GameData.Players[i].Nationality = ReadString(reader, 11);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					this.parent.GameData.Players[i].Coins = ReadInt16(reader);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					this.parent.GameData.Players[i].ResearchProgress = ReadInt16(reader);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					for (int j = 0; j < this.parent.GameData.Players[i].ActiveUnits.Length; j++)
					{
						this.parent.GameData.Players[i].ActiveUnits[j] = ReadInt16(reader);
					}
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					for (int j = 0; j < this.parent.GameData.Players[i].UnitsInProduction.Length; j++)
					{
						this.parent.GameData.Players[i].UnitsInProduction[j] = ReadInt16(reader);
					}
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					this.parent.GameData.Players[i].DiscoveredTechnologyCount = ReadInt16(reader);
				}

				for (int i = 0; i < 8; i++)
				{
					for (int j = 0; j < 5; j++)
					{
						this.parent.GameData.Players[i].DiscoveredTechnologyFlags[j] = ReadUInt16(reader);
					}
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					this.parent.GameData.Players[i].GovernmentType = ReadInt16(reader);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					for (int j = 0; j < this.parent.GameData.Players[i].Continents.Length; j++)
					{
						this.parent.GameData.Players[i].Continents[j].Strategy = (PlayerContinentStrategyEnum)ReadInt16(reader);
					}
				}

				for (int i = 0; i < 8; i++)
				{
					for (int j = 0; j < 8; j++)
					{
						this.parent.GameData.Players[i].Diplomacy[j] = (DiplomacyFlagsEnum)ReadUInt16(reader);
					}
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					this.parent.GameData.Players[i].CityCount = ReadInt16(reader);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					this.parent.GameData.Players[i].UnitCount = ReadInt16(reader);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					this.parent.GameData.Players[i].MapCellCount = ReadInt16(reader);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					this.parent.GameData.Players[i].SettlerCount = ReadInt16(reader);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					this.parent.GameData.Players[i].TotalCitySize = ReadInt16(reader);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					this.parent.GameData.Players[i].MilitaryPower = ReadInt16(reader);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					this.parent.GameData.Players[i].Ranking = ReadInt16(reader);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					this.parent.GameData.Players[i].TaxRate = ReadInt16(reader);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					this.parent.GameData.Players[i].Score = ReadInt16(reader);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					this.parent.GameData.Players[i].ContactPlayerCountdown = ReadInt16(reader);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					this.parent.GameData.Players[i].XStart = ReadInt16(reader);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					this.parent.GameData.Players[i].NationalityID = ReadInt16(reader);
				}

				for (int i = 0; i < 8; i++)
				{
					for (int j = 0; j < 16; j++)
					{
						this.parent.GameData.Players[i].Continents[j].Attack = ReadInt16(reader);
					}
				}

				for (int i = 0; i < 8; i++)
				{
					for (int j = 0; j < 16; j++)
					{
						this.parent.GameData.Players[i].Continents[j].Defense = ReadInt16(reader);
					}
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					for (int j = 0; j < this.parent.GameData.Players[i].Continents.Length; j++)
					{
						this.parent.GameData.Players[i].Continents[j].CityCount = ReadInt16(reader);
					}
				}

				for (int i = 0; i < 16; i++)
				{
					this.parent.GameData.Continents[i].Size = ReadInt16(reader);
				}
				reader.Seek(48 * 2, SeekOrigin.Current);

				for (int i = 0; i < 16; i++)
				{
					this.parent.GameData.Oceans[i].Size = ReadInt16(reader);
				}
				reader.Seek(48 * 2, SeekOrigin.Current);

				for (int i = 0; i < 16; i++)
				{
					this.parent.GameData.Continents[i].BuildSiteCount = ReadInt16(reader);
				}

				for (int i = 0; i < 1200; i++)
				{
					this.parent.GameData.ScoreGraphData[i] = ReadUInt8(reader);
				}

				for (int i = 0; i < this.parent.GameData.PeaceGraphData.Length; i++)
				{
					this.parent.GameData.PeaceGraphData[i] = ReadUInt8(reader);
				}

				for (int i = 0; i < this.parent.GameData.Cities.Length; i++)
				{
					this.parent.GameData.Cities[i] = City.FromStream(i, reader);
				}

				for (int i = 0; i < 28; i++)
				{
					this.parent.GameData.Units[i] = UnitDefinition.FromStream(reader);
				}

				for (int i = 0; i < 8; i++)
				{
					for (int j = 0; j < 128; j++)
					{
						Unit unit = Unit.FromStream(j, reader);
						unit.PlayerID = (short)i;
						this.parent.GameData.Players[i].Units[j] = unit;
					}
				}

				for (int i = 0; i < 80; i++)
				{
					for (int j = 0; j < 50; j++)
					{
						this.parent.GameData.MapVisibility[i, j] = (ushort)((short)((sbyte)ReadUInt8(reader)));
					}
				}

				for (int i = 0; i < 8; i++)
				{
					for (int j = 0; j < 16; j++)
					{
						this.parent.GameData.Players[i].ContinentPolicies[j].UnitRoleType = (UnitRoleTypeEnum)((sbyte)ReadUInt8(reader));
					}
				}

				for (int i = 0; i < 8; i++)
				{
					for (int j = 0; j < 16; j++)
					{
						this.parent.GameData.Players[i].ContinentPolicies[j].Policy = (sbyte)ReadUInt8(reader);
					}
				}

				for (int i = 0; i < 8; i++)
				{
					for (int j = 0; j < 16; j++)
					{
						this.parent.GameData.Players[i].ContinentPolicies[j].Position =new((sbyte)ReadUInt8(reader),0);
					}
				}

				for (int i = 0; i < 8; i++)
				{
					for (int j = 0; j < 16; j++)
					{
						this.parent.GameData.Players[i].ContinentPolicies[j].Position = new(this.parent.GameData.Players[i].ContinentPolicies[j].Position.X, (sbyte)ReadUInt8(reader));
					}
				}

				for (int i = 0; i < this.parent.GameData.TechnologyFirstDiscoveredBy.Length; i++)
				{
					this.parent.GameData.TechnologyFirstDiscoveredBy[i] = ReadInt16(reader);
				}

				for (int i = 0; i < 8; i++)
				{
					for (int j = 0; j < 8; j++)
					{
						this.parent.GameData.Players[i].UnitsDestroyed[j] = ReadInt16(reader);
					}
				}

				for (int i = 0; i < this.parent.GameData.CityNames.Length; i++)
				{
					this.parent.GameData.CityNames[i] = ReadString(reader, 13);
				}

				this.parent.GameData.ReplayDataLength = ReadInt16(reader);

				for (int i = 0; i < this.parent.GameData.ReplayData.Length; i++)
				{
					this.parent.GameData.ReplayData[i] = ReadUInt8(reader);
				}

				for (int i = 0; i < this.parent.GameData.WonderCityID.Length; i++)
				{
					this.parent.GameData.WonderCityID[i] = ReadInt16(reader);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					for (int j = 0; j < this.parent.GameData.Players[i].LostUnits.Length; j++)
					{
						this.parent.GameData.Players[i].LostUnits[j] = ReadInt16(reader);

					}
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					for (int j = 0; j < this.parent.GameData.Players[i].TechnologyAcquiredFrom.Length; j++)
					{
						this.parent.GameData.Players[i].TechnologyAcquiredFrom[j] = (sbyte)ReadUInt8(reader);
					}
				}

				this.parent.GameData.PollutedSquareCount = ReadInt16(reader);
				this.parent.GameData.PollutionEffectLevel = ReadInt16(reader);
				this.parent.GameData.GlobalWarmingCount = ReadInt16(reader);
				this.parent.GameData.GameSettingFlags.Value = ReadInt16(reader);
				this.parent.CommonTools.SetSoundEnabled(
					this.parent.GameData.GameSettingFlags.Sound);

				//reader.Seek(260, SeekOrigin.Current); // Skip corrupted Land path data
				int[,] landPath = this.parent.UnitGoTo.Arr_db44_LandPath;

				for (int i = 0; i < 20; i++)
				{
					for (int j = 0; j < 13; j++)
					{
						landPath[i, j] = ReadUInt8(reader);
					}
				}

				this.parent.GameData.MaximumTechnologyCount = ReadInt16(reader);
				this.parent.GameData.Players[this.parent.GameData.HumanPlayerID].FutureTechnologyCount = ReadInt16(reader);
				this.parent.GameData.DebugFlags = ReadInt16(reader);

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					this.parent.GameData.Players[i].ScienceTaxRate = ReadInt16(reader);
				}
				
				this.parent.GameData.NextPlayerHistoryRankingTurn = ReadInt16(reader);

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					this.parent.GameData.Players[i].HistoryRankingScore = ReadInt16(reader);
				}

				for (int i = 0; i < 8; i++)
				{
					byte[] buffer = new byte[180];
					reader.Read(buffer, 0, 180);

					for (int j = 0; j < 180; j++)
					{
						this.parent.GameData.Players[i].SpaceshipData[j] = (sbyte)buffer[j];
					}
				}

				this.parent.GameData.SpaceshipFlags = ReadInt16(reader);
				this.parent.GameData.Players[this.parent.GameData.HumanPlayerID].SpaceshipSuccessRate = ReadInt16(reader);
				this.parent.GameData.AISpaceshipSuccessRate = ReadInt16(reader);

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					this.parent.GameData.Players[i].SpaceshipETAYear = ReadInt16(reader);
				}

				for (int i = 0; i < 12; i++)
				{
					this.parent.GameData.Players[this.parent.GameData.HumanPlayerID].PalaceData1[i + 2] = ReadInt16(reader);
				}

				for (int i = 0; i < 12; i++)
				{
					this.parent.GameData.Players[this.parent.GameData.HumanPlayerID].PalaceData2[i] = ReadInt16(reader);
				}

				for (int i = 0; i < this.parent.GameData.CityPositions.Length; i++)
				{
					this.parent.GameData.CityPositions[i] = new((sbyte)ReadUInt8(reader), 0);
				}

				for (int i = 0; i < this.parent.GameData.CityPositions.Length; i++)
				{
					this.parent.GameData.CityPositions[i] = new(this.parent.GameData.CityPositions[i].X, (sbyte)ReadUInt8(reader));
				}

				this.parent.GameData.Players[this.parent.GameData.HumanPlayerID].PalaceLevel = ReadInt16(reader);
				this.parent.GameData.PeaceTurnCount = ReadInt16(reader);
				this.parent.GameData.AIOpponentCount = ReadInt16(reader);

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					this.parent.GameData.Players[i].SpaceshipPopulation = ReadInt16(reader);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					this.parent.GameData.Players[i].SpaceshipLaunchYear = ReadInt16(reader);
				}

				this.parent.GameData.PlayerIdentityFlags = ReadInt16(reader);

				bSuccess = true;
			}
			catch (Exception ex)
			{
				TryWriteLoadFailureLog(
					filenameWithoutExtension,
					ex);
				bSuccess = false;
			}

			return bSuccess;
		}

		private ValidatedSaveBundle ReadAndValidateBundle(
			ClassicSaveBundlePaths bundle)
		{
			byte[] stateBytes =
				File.ReadAllBytes(bundle.StatePath);
			byte[] mapBytes =
				File.ReadAllBytes(bundle.MapPath);
			if (stateBytes.Length !=
				ClassicSavePayloadContract.StateByteLength)
			{
				throw new InvalidDataException(
					"Classic save state payload has an invalid size.");
			}
			ValidateStateSummaryFields(stateBytes);
			GBitmap? map = GBitmap.FromPICBytes(
				mapBytes,
				preferHiColor: true);
			if (map is null ||
				map.Width != 320 ||
				map.Height != 200)
			{
				throw new InvalidDataException(
					"Classic save map payload must be a valid 320x200 PIC.");
			}
			if (!File.Exists(bundle.MetadataPath))
			{
				return new ValidatedSaveBundle(
					ClassicAiProfile.Classic1991,
					stateBytes,
					mapBytes,
					ClassicUnitAutomationMetadata.Empty,
					MetadataSchemaVersion: null,
					HasMetadata: false);
			}

			byte[] metadataBytes =
				ReadMetadataBytes(bundle.MetadataPath);

			using MemoryStream stateReader = new(
				stateBytes,
				writable: false);
			stateReader.Seek(6, SeekOrigin.Begin);
			ushort seed = ReadUInt16(stateReader);
			stateReader.Seek(10, SeekOrigin.Begin);
			short difficultyLevel = ReadInt16(stateReader);

			ClassicSaveMetadata metadata =
				SaveMetadataSerializer.DeserializeAndValidate(
					metadataBytes,
					stateBytes,
					mapBytes,
					ClassicRuntimeCompatibilityIds.Current,
					ClassicDifficultyIds.ToStableId(
						difficultyLevel),
					seed);
			if (!ClassicAiRuntimeProfiles.IsSupported(
					metadata.AiProfile))
			{
				throw new SaveProfileUnavailableException(
					$"AI profile '{metadata.AiProfileId}' is not available in this Classic runtime.");
			}

			return new ValidatedSaveBundle(
				metadata.AiProfile,
				stateBytes,
				mapBytes,
				metadata.UnitAutomation,
				metadata.SchemaVersion,
				HasMetadata: true);
		}

		private void ValidateStateSummaryFields(
			byte[] stateBytes)
		{
			using MemoryStream reader = new(
				stateBytes,
				writable: false);
			reader.Seek(2, SeekOrigin.Begin);
			int humanPlayerID = ReadInt16(reader);
			if (humanPlayerID < 0 ||
				humanPlayerID >=
					this.parent.GameData.Players.Length)
			{
				throw new InvalidDataException(
					"Classic save human player ID is outside the supported range.");
			}

			reader.Seek(
				16 + (humanPlayerID * 14),
				SeekOrigin.Begin);
			ValidateSummaryText(
				ReadString(reader, 14),
				"player name");
			reader.Seek(
				128 + (humanPlayerID * 12),
				SeekOrigin.Begin);
			ValidateSummaryText(
				ReadString(reader, 12),
				"nation name");
		}

		private static void ValidateSummaryText(
			string text,
			string fieldName)
		{
			foreach (char character in text)
			{
				if (character < ' ' || character > '~')
				{
					throw new InvalidDataException(
						$"Classic save {fieldName} contains a non-renderable character.");
				}
			}
		}

		private static byte[] ReadMetadataBytes(string metadataPath)
		{
			using FileStream stream = new(
				metadataPath,
				FileMode.Open,
				FileAccess.Read,
				FileShare.Read);
			long length = stream.Length;
			if (length <= 0 ||
				length >
					ClassicSaveMetadataSerializer
						.MaximumJsonByteLength)
			{
				throw new InvalidDataException(
					"Classic save metadata JSON has an invalid size.");
			}

			byte[] metadataBytes = new byte[(int)length];
			stream.ReadExactly(metadataBytes);
			if (stream.ReadByte() >= 0)
			{
				throw new InvalidDataException(
					"Classic save metadata changed while it was read.");
			}

			return metadataBytes;
		}

		private sealed record ValidatedSaveBundle(
			ClassicAiProfile AiProfile,
			byte[] StateBytes,
			byte[] MapBytes,
			ClassicUnitAutomationMetadata UnitAutomation,
			int? MetadataSchemaVersion,
			bool HasMetadata);

		private static ClassicAiProfile GetStoredBundleProfile(
			ValidatedSaveBundle bundle) =>
			IsPreProfileSplitProject1991Bundle(bundle) ||
				bundle.AiProfile ==
					ClassicAiProfile.Smart1991Plus ||
				bundle.UnitAutomation.Orders.Count > 0
				? ClassicAiProfile.Smart1991Plus
				: ClassicAiProfile.Classic1991;

		private static bool IsPreProfileSplitProject1991Bundle(
			ValidatedSaveBundle bundle) =>
			bundle.HasMetadata &&
			bundle.MetadataSchemaVersion is >=
				ClassicSaveMetadata.LegacySchemaVersion and <
				ClassicSaveMetadata.ProfileSplitSchemaVersion;

		private void EnableSmartAutomationDefaultsForLegacyBundle(
			ValidatedSaveBundle bundle)
		{
			if (bundle.HasMetadata &&
				bundle.MetadataSchemaVersion is >=
					ClassicSaveMetadata.LegacySchemaVersion and <
					ClassicSaveMetadata.CurrentSchemaVersion &&
				!this.parent.GameData.GameSettingFlags
					.HasSmartAutomationOptionEnabled())
			{
				this.parent.GameData.GameSettingFlags
					.EnableSmartAutomationDefaults();
			}
		}

		private ClassicAiProfile ResolveLoadedProfile(
			ValidatedSaveBundle bundle)
		{
			if (!ClassicAiRuntimeProfiles.IsSupported(
					bundle.AiProfile))
			{
				throw new SaveProfileUnavailableException(
					$"AI profile '{GetAiProfileDiagnosticId(bundle.AiProfile)}' is not available.");
			}

			// Every P91 metadata schema predating the explicit product split
			// belongs to the former combined Project1991 mode, even when no
			// optional order happened to be active at save time. Metadata-free
			// Civ1/OpenCivOne saves remain original unless their otherwise
			// unused high setting bits prove Project1991 enhancements.
			if (IsPreProfileSplitProject1991Bundle(bundle) ||
				bundle.AiProfile ==
					ClassicAiProfile.Smart1991Plus ||
				bundle.UnitAutomation.Orders.Count > 0 ||
				this.parent.GameData.GameSettingFlags
					.Has1991PlusOptionsEnabled())
			{
				return ClassicAiProfile.Smart1991Plus;
			}

			return ClassicAiProfile.Classic1991;
		}

		private void EnableOptionsRequiredByOrders(
			ClassicUnitAutomationMetadata metadata)
		{
			foreach (ClassicUnitAutomationOrderMetadata order in
				metadata.Orders)
			{
				switch (order.Kind)
				{
					case ClassicUnitAutomationKind.AutomaticExplore:
						this.parent.GameData.GameSettingFlags
							.AutomaticExplore = true;
						break;
					case ClassicUnitAutomationKind.ImproveNearestCity:
						this.parent.GameData.GameSettingFlags
							.ImproveNearestCity = true;
						break;
					case ClassicUnitAutomationKind.BuildRoadToCity:
						this.parent.GameData.GameSettingFlags
							.BuildRoadToCity = true;
						break;
				}
			}
		}

		private sealed class SaveProfileUnavailableException :
			Exception
		{
			public SaveProfileUnavailableException(
				string message)
				: base(message)
			{
			}
		}

		/// <summary>
		/// ?
		/// </summary>
		/// <param name="reader"></param>
		/// <returns></returns>
		public static byte ReadUInt8(Stream reader)
		{
			return ReadRequiredByte(reader);
		}

		/// <summary>
		/// Reads a UInt16 from a Stream
		/// </summary>
		/// <param name="reader"></param>
		/// <returns></returns>
		public static ushort ReadUInt16(Stream reader)
		{
			byte byte0 = ReadRequiredByte(reader);
			byte byte1 = ReadRequiredByte(reader);
			return (ushort)(byte0 | (byte1 << 8));
		}

		/// <summary>
		/// ?
		/// </summary>
		/// <param name="reader"></param>
		/// <returns></returns>
		public static short ReadInt16(Stream reader)
		{
			return unchecked((short)ReadUInt16(reader));
		}

		/// <summary>
		/// Reads a UInt32 from a Stream
		/// </summary>
		/// <param name="reader"></param>
		/// <returns></returns>
		public static uint ReadUInt32(Stream reader)
		{
			uint byte0 = ReadRequiredByte(reader);
			uint byte1 = ReadRequiredByte(reader);
			uint byte2 = ReadRequiredByte(reader);
			uint byte3 = ReadRequiredByte(reader);
			return byte0 | (byte1 << 8) | (byte2 << 16) | (byte3 << 24);
		}

		/// <summary>
		/// Reads a null terminated string from the stream (null character included)
		/// </summary>
		/// <param name="reader">Reading stream</param>
		/// <param name="length">Full string length, including null character</param>
		/// <returns></returns>
		public static string ReadString(Stream reader, int length)
		{
			ArgumentOutOfRangeException.ThrowIfNegativeOrZero(length);

			int len = 0;
			char[] str = new char[length];
			bool end = false;

			for (int i = 0; i < length - 1; i++)
			{
				byte ch = ReadRequiredByte(reader);

				if (!end)
				{
					if (ch == 0)
					{
						end = true;
					}
					else
					{
						str[len] = (char)ch;
						len++;
					}
				}
			}

			ReadRequiredByte(reader);

			return new string(str, 0, len);
		}

		private static byte ReadRequiredByte(Stream reader)
		{
			int value = reader.ReadByte();
			if (value < 0)
			{
				throw new EndOfStreamException(
					"Unexpected end of Classic save data.");
			}

			return (byte)value;
		}

		/// <summary>
		/// ?
		/// </summary>
		/// <param name="filename"></param>
		/// <returns></returns>
		public bool F11_0000_08f6_SaveGameData(string filename)
		{
			return SaveGameData(filename, showFailureDialog: true);
		}

		private bool SaveGameData(
			string filename,
			bool showFailureDialog)
		{
			filename = filename.ToUpper();

			//this.CPU.Log.EnterBlock($"F11_0000_08f6_SaveGameData('{filename}')");

			// function body
			bool bSuccess = false;
			string filenameWithoutExtension = Path.GetFileNameWithoutExtension(CAPI.GetDOSFileName(filename));

			if (!ClassicAiRuntimeProfiles.IsSupported(
					this.parent.GameData.AiProfile))
			{
				TryWriteSaveFailureLog(
					filename,
					new InvalidOperationException(
						$"AI profile '{GetAiProfileDiagnosticId(this.parent.GameData.AiProfile)}' is not available."));
				return false;
			}

			if (this.parent.GameData.AiProfile ==
					ClassicAiProfile.Classic1991 &&
				(this.parent.GameData.GameSettingFlags
						.Has1991PlusOptionsEnabled() ||
					this.parent.UnitAutomationState.Count > 0))
			{
				TryWriteSaveFailureLog(
					filename,
					new InvalidOperationException(
						"Original 1991 cannot save Project1991-only options or unit orders."));
				return false;
			}

			try
			{
				this.savePairFiles.WriteBundle(
					filenameWithoutExtension,
					temporaryBundle =>
					{
				// write map file
				this.parent.GameData.Map.SaveToPIC(
					temporaryBundle.MapPath,
					false);

				// write sve file
				using FileStream writer = new(
					temporaryBundle.StatePath,
					FileMode.Create,
					FileAccess.Write);
				WriteInt16(writer, this.parent.GameData.TurnCount);
				WriteInt16(writer, this.parent.GameData.HumanPlayerID);
				WriteInt16(writer, this.parent.GameData.PlayerFlags);
				WriteUInt16(writer, this.parent.GameData.RandomSeed);
				WriteInt16(writer, this.parent.GameData.Year);
				WriteInt16(writer, this.parent.GameData.DifficultyLevel);
				WriteInt16(writer, this.parent.GameData.ActiveCivilizations);
				WriteInt16(writer, this.parent.GameData.Players[this.parent.GameData.HumanPlayerID].ResearchTechnologyID);

				for (int i = 0; i < 8; i++)
				{
					WriteString(writer, this.parent.GameData.Players[i].Name, 14);
				}

				for (int i = 0; i < 8; i++)
				{
					WriteString(writer, this.parent.GameData.Players[i].Nation, 12);
				}

				for (int i = 0; i < 8; i++)
				{
					WriteString(writer, this.parent.GameData.Players[i].Nationality, 11);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					WriteInt16(writer, this.parent.GameData.Players[i].Coins);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					WriteInt16(writer, this.parent.GameData.Players[i].ResearchProgress);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					for (int j = 0; j < this.parent.GameData.Players[i].ActiveUnits.Length; j++)
					{
						WriteInt16(writer, this.parent.GameData.Players[i].ActiveUnits[j]);
					}
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					for (int j = 0; j < this.parent.GameData.Players[i].UnitsInProduction.Length; j++)
					{
						WriteInt16(writer, this.parent.GameData.Players[i].UnitsInProduction[j]);
					}
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					WriteInt16(writer, this.parent.GameData.Players[i].DiscoveredTechnologyCount);
				}

				for (int i = 0; i < 8; i++)
				{
					for (int j = 0; j < 5; j++)
					{
						WriteUInt16(writer, this.parent.GameData.Players[i].DiscoveredTechnologyFlags[j]);
					}
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					WriteInt16(writer, this.parent.GameData.Players[i].GovernmentType);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					for (int j = 0; j < this.parent.GameData.Players[i].Continents.Length; j++)
					{
						WriteInt16(writer, (short)this.parent.GameData.Players[i].Continents[j].Strategy);
					}
				}

				for (int i = 0; i < 8; i++)
				{
					for (int j = 0; j < 8; j++)
					{
						WriteUInt16(writer, (ushort)this.parent.GameData.Players[i].Diplomacy[j]);
					}
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					WriteInt16(writer, this.parent.GameData.Players[i].CityCount);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					WriteInt16(writer, this.parent.GameData.Players[i].UnitCount);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					WriteInt16(writer, this.parent.GameData.Players[i].MapCellCount);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					WriteInt16(writer, this.parent.GameData.Players[i].SettlerCount);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					WriteInt16(writer, this.parent.GameData.Players[i].TotalCitySize);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					WriteInt16(writer, this.parent.GameData.Players[i].MilitaryPower);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					WriteInt16(writer, this.parent.GameData.Players[i].Ranking);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					WriteInt16(writer, this.parent.GameData.Players[i].TaxRate);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					WriteInt16(writer, this.parent.GameData.Players[i].Score);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					WriteInt16(writer, this.parent.GameData.Players[i].ContactPlayerCountdown);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					WriteInt16(writer, this.parent.GameData.Players[i].XStart);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					WriteInt16(writer, this.parent.GameData.Players[i].NationalityID);
				}

				for (int i = 0; i < 8; i++)
				{
					for (int j = 0; j < 16; j++)
					{
						WriteInt16(writer, this.parent.GameData.Players[i].Continents[j].Attack);
					}
				}

				for (int i = 0; i < 8; i++)
				{
					for (int j = 0; j < 16; j++)
					{
						WriteInt16(writer, this.parent.GameData.Players[i].Continents[j].Defense);
					}
				}
				
				for (int i = 0; i < 8; i++)
				{
					for (int j = 0; j < 16; j++)
					{
						WriteInt16(writer, this.parent.GameData.Players[i].Continents[j].CityCount);
					}
				}

				for (int i = 0; i < 16; i++)
				{
					WriteInt16(writer, this.parent.GameData.Continents[i].Size);
				}

				for (int i = 0; i < 48; i++)
				{
					WriteInt16(writer, 0);
				}

				for (int i = 0; i < 16; i++)
				{
					WriteInt16(writer, this.parent.GameData.Oceans[i].Size);
				}

				for (int i = 0; i < 48; i++)
				{
					WriteInt16(writer, 0);
				}

				for (int i = 0; i < 16; i++)
				{
					WriteInt16(writer, this.parent.GameData.Continents[i].BuildSiteCount);
				}

				for (int i = 0; i < 1200; i++)
				{
					writer.WriteByte(this.parent.GameData.ScoreGraphData[i]);
				}

				for (int i = 0; i < this.parent.GameData.PeaceGraphData.Length; i++)
				{
					writer.WriteByte(this.parent.GameData.PeaceGraphData[i]);
				}

				for (int i = 0; i < this.parent.GameData.Cities.Length; i++)
				{
					this.parent.GameData.Cities[i].ToStream(writer);
				}

				for (int i = 0; i < 28; i++)
				{
					this.parent.GameData.Units[i].ToStream(writer);
				}

				for (int i = 0; i < 8; i++)
				{
					for (int j = 0; j < 128; j++)
					{
						this.parent.GameData.Players[i].Units[j].ToStream(writer);
					}
				}

				for (int i = 0; i < 80; i++)
				{
					for (int j = 0; j < 50; j++)
					{
						writer.WriteByte((byte)((sbyte)((short)this.parent.GameData.MapVisibility[i, j])));
					}
				}

				for (int i = 0; i < 8; i++)
				{
					for (int j = 0; j < 16; j++)
					{
						writer.WriteByte((byte)((sbyte)this.parent.GameData.Players[i].ContinentPolicies[j].UnitRoleType));
					}
				}

				for (int i = 0; i < 8; i++)
				{
					for (int j = 0; j < 16; j++)
					{
						writer.WriteByte((byte)((sbyte)this.parent.GameData.Players[i].ContinentPolicies[j].Policy));
					}
				}

				for (int i = 0; i < 8; i++)
				{
					for (int j = 0; j < 16; j++)
					{
						writer.WriteByte((byte)this.parent.GameData.Players[i].ContinentPolicies[j].Position.X);
					}
				}

				for (int i = 0; i < 8; i++)
				{
					for (int j = 0; j < 16; j++)
					{
						writer.WriteByte((byte)this.parent.GameData.Players[i].ContinentPolicies[j].Position.Y);
					}
				}

				for (int i = 0; i < this.parent.GameData.TechnologyFirstDiscoveredBy.Length; i++)
				{
					WriteInt16(writer, this.parent.GameData.TechnologyFirstDiscoveredBy[i]);
				}

				for (int i = 0; i < 8; i++)
				{
					for (int j = 0; j < 8; j++)
					{
						WriteInt16(writer, this.parent.GameData.Players[i].UnitsDestroyed[j]);
					}
				}

				for (int i = 0; i < this.parent.GameData.CityNames.Length; i++)
				{
					WriteString(writer, this.parent.GameData.CityNames[i], 13);
				}

				WriteInt16(writer, this.parent.GameData.ReplayDataLength);
				for (int i = 0; i < this.parent.GameData.ReplayData.Length; i++)
				{
					writer.WriteByte(this.parent.GameData.ReplayData[i]);
				}

				for (int i = 0; i < this.parent.GameData.WonderCityID.Length; i++)
				{
					WriteInt16(writer, this.parent.GameData.WonderCityID[i]);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					for (int j = 0; j < this.parent.GameData.Players[i].LostUnits.Length; j++)
					{
						WriteInt16(writer, this.parent.GameData.Players[i].LostUnits[j]);
					}
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					for (int j = 0; j < this.parent.GameData.Players[i].TechnologyAcquiredFrom.Length; j++)
					{
						writer.WriteByte((byte)((sbyte)this.parent.GameData.Players[i].TechnologyAcquiredFrom[j]));
					}
				}

				WriteInt16(writer, this.parent.GameData.PollutedSquareCount);
				WriteInt16(writer, this.parent.GameData.PollutionEffectLevel);
				WriteInt16(writer, this.parent.GameData.GlobalWarmingCount);
				WriteInt16(writer, (short)this.parent.GameData.GameSettingFlags.Value);

				int[,] landPath = this.parent.UnitGoTo.Arr_db44_LandPath;

				for (int i = 0; i < 20; i++)
				{
					for (int j = 0; j < 13; j++)
					{
						writer.WriteByte((byte)landPath[i, j]);
					}
				}

				WriteInt16(writer, this.parent.GameData.MaximumTechnologyCount);
				WriteInt16(writer, this.parent.GameData.Players[this.parent.GameData.HumanPlayerID].FutureTechnologyCount);
				WriteInt16(writer, this.parent.GameData.DebugFlags);

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					WriteInt16(writer, this.parent.GameData.Players[i].ScienceTaxRate);
				}
				
				WriteInt16(writer, this.parent.GameData.NextPlayerHistoryRankingTurn);

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					WriteInt16(writer, this.parent.GameData.Players[i].HistoryRankingScore);
				}

				for (int i = 0; i < 8; i++)
				{
					byte[] buffer = new byte[180];

					for (int j = 0; j < 180; j++)
					{
						buffer[j] = (byte)this.parent.GameData.Players[i].SpaceshipData[j];
					}

					writer.Write(buffer, 0, 180);
				}

				WriteInt16(writer, this.parent.GameData.SpaceshipFlags);
				WriteInt16(writer, this.parent.GameData.Players[this.parent.GameData.HumanPlayerID].SpaceshipSuccessRate);
				WriteInt16(writer, this.parent.GameData.AISpaceshipSuccessRate);

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					WriteInt16(writer, this.parent.GameData.Players[i].SpaceshipETAYear);
				}

				for (int i = 0; i < 12; i++)
				{
					WriteInt16(writer, (short)this.parent.GameData.Players[this.parent.GameData.HumanPlayerID].PalaceData1[i + 2]);
				}

				for (int i = 0; i < 12; i++)
				{
					WriteInt16(writer, (short)this.parent.GameData.Players[this.parent.GameData.HumanPlayerID].PalaceData2[i]);
				}

				for (int i = 0; i < 256; i++)
				{
					writer.WriteByte((byte)((sbyte)this.parent.GameData.CityPositions[i].X));
				}
				for (int i = 0; i < 256; i++)
				{
					writer.WriteByte((byte)((sbyte)this.parent.GameData.CityPositions[i].Y));
				}

				WriteInt16(writer, this.parent.GameData.Players[this.parent.GameData.HumanPlayerID].PalaceLevel);
				WriteInt16(writer, this.parent.GameData.PeaceTurnCount);
				WriteInt16(writer, this.parent.GameData.AIOpponentCount);

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					WriteInt16(writer, this.parent.GameData.Players[i].SpaceshipPopulation);
				}

				for (int i = 0; i < this.parent.GameData.Players.Length; i++)
				{
					WriteInt16(writer, this.parent.GameData.Players[i].SpaceshipLaunchYear);
				}

				WriteInt16(writer, this.parent.GameData.PlayerIdentityFlags);

				writer.Close();

				byte[] stateBytes =
					File.ReadAllBytes(temporaryBundle.StatePath);
				byte[] mapBytes =
					File.ReadAllBytes(temporaryBundle.MapPath);
				ClassicSaveMetadata metadata =
					SaveMetadataSerializer.Create(
						this.parent.GameData.AiProfile,
						ClassicRuntimeCompatibilityIds.Current,
						ClassicDifficultyIds.ToStableId(
							this.parent.GameData.DifficultyLevel),
						this.parent.GameData.RandomSeed,
						stateBytes,
						mapBytes,
						[],
						this.parent.UnitAutomationState
							.CreateSaveMetadata(
								this.parent.GameData));
				File.WriteAllBytes(
					temporaryBundle.MetadataPath,
					SaveMetadataSerializer.Serialize(metadata));
					});

				bSuccess = true;
			}
			catch (Exception ex)
			{
				TryWriteSaveFailureLog(filename, ex);

				if (showFailureDialog)
				{
					try
					{
						this.parent.MenuBoxDialog.F0_2d05_0031_ShowMenuBox(
							ex.Message,
							4,
							64,
							true,
							false,
							true);
					}
					catch (Exception dialogException)
					{
						// A transient report style must not turn a recoverable
						// save failure into a game-ending presentation crash.
						TryWriteSaveFailureLog(
							filename,
							new AggregateException(
								"The save failure dialog could not be displayed.",
								ex,
								dialogException));
					}
				}

				bSuccess = false;
			}

			return bSuccess;
		}

		private void TryWriteSaveFailureLog(
			string filename,
			Exception exception)
		{
			try
			{
				string logPath =
					this.parent.RuntimeOptions.GetLogFilePath(
						"SaveError.log");
				File.AppendAllText(
					logPath,
					$"---------------------------{Environment.NewLine}" +
					$"Time: {DateTimeOffset.Now:O}{Environment.NewLine}" +
					$"Save: {filename}{Environment.NewLine}" +
					$"{exception}{Environment.NewLine}",
					Encoding.UTF8);
			}
			catch
			{
				// Saving stays non-fatal even when the diagnostic path itself
				// is unavailable. ClassicSavePairFiles keeps the prior pair.
			}
		}

		private void TryWriteLoadFailureLog(
			string filename,
			Exception exception)
		{
			try
			{
				string logPath =
					this.parent.RuntimeOptions.GetLogFilePath(
						"LoadError.log");
				File.AppendAllText(
					logPath,
					$"---------------------------{Environment.NewLine}" +
					$"Time: {DateTimeOffset.Now:O}{Environment.NewLine}" +
					$"Save: {filename}{Environment.NewLine}" +
					$"{exception}{Environment.NewLine}",
					Encoding.UTF8);
			}
			catch
			{
				// A rejected sidecar must remain non-fatal even when the
				// diagnostic path is unavailable.
			}
		}

		private static string GetAiProfileDiagnosticId(
			ClassicAiProfile aiProfile) =>
			aiProfile switch
			{
				ClassicAiProfile.Classic1991 =>
					ClassicAiProfileIds.Classic1991,
				ClassicAiProfile.Smart1991Plus =>
					ClassicAiProfileIds.Smart1991Plus,
				_ => $"unknown:{(int)aiProfile}",
			};

		/// <summary>
		/// ?
		/// </summary>
		/// <param name="writer"></param>
		/// <param name="value"></param>
		public static void WriteUInt16(Stream writer, ushort value)
		{
			writer.WriteByte((byte)(value & 0xff));
			writer.WriteByte((byte)((value & 0xff00) >> 8));
		}

		/// <summary>
		/// Writes an Int16 to a Stream
		/// </summary>
		/// <param name="writer"></param>
		/// <param name="value"></param>
		public static void WriteInt16(Stream writer, short value)
		{
			writer.WriteByte((byte)((ushort)value & 0xff));
			writer.WriteByte((byte)(((ushort)value & 0xff00) >> 8));
		}

		/// <summary>
		/// Writes an UInt32 to a Stream
		/// </summary>
		/// <param name="writer"></param>
		/// <param name="value"></param>
		public static void WriteUInt32(Stream writer, uint value)
		{
			writer.WriteByte((byte)(value & 0xff));
			writer.WriteByte((byte)((value & 0xff00) >> 8));
			writer.WriteByte((byte)((value & 0xff0000) >> 16));
			writer.WriteByte((byte)((value & 0xff000000) >> 24));
		}

		/// <summary>
		/// Writes a null terminated string to a stream. Null character is included in the string length
		/// </summary>
		/// <param name="writer">Writer</param>
		/// <param name="text">String to write</param>
		/// <param name="length">maximum string length including the null character</param>
		public static void WriteString(Stream writer, string text, int length)
		{
			bool end = false;

			for (int i = 0; i < length - 1; i++)
			{
				if (!end && i < text.Length)
				{
					if (text[i] == 0)
					{
						end = true;
						writer.WriteByte(0);
					}
					else
					{
						writer.WriteByte((byte)text[i]);
					}
				}
				else
				{
					writer.WriteByte(0);
				}
			}

			writer.WriteByte(0);
		}
	}
}
