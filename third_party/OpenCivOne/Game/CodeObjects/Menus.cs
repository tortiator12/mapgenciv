using System.Text;
using OpenCivOne.Localization;
using OpenCivOne.Platform;
using OpenCivOne.Runtime;

namespace OpenCivOne
{
	public class Menus
	{
		private OpenCivOneGame parent;

		// Local variables used exclusively inside this section
		private short Var_654a = 0;

		// public variables
		public int Var_d4ca_MenuShortcutKey = 0;
		private bool goToPathOverlayRefreshRequested;

		public Menus(OpenCivOneGame parent)
		{
			this.parent = parent;
		}

		public bool ConsumeGoToPathOverlayRefreshRequest()
		{
			bool requested = this.goToPathOverlayRefreshRequested;
			this.goToPathOverlayRefreshRequested = false;
			return requested;
		}

		/// <summary>
		/// Shows and handles one of the five top menus: Game, Orders, Advisors, World and Encyclopedia
		/// </summary>
		/// <param name="playerID"></param>
		/// <param name="unitID"></param>
		/// <param name="menuIndex">Index of specific menu to show or -1 to select menu using current mouse X coordinate</param>
		public void F0_2c84_0000_ShowTopMenu(int playerID, int unitID, int menuIndex)
		{
			//this.oCPU.Log.EnterBlock($"F0_2c84_0000_ShowTopMenu({playerID}, {unitID}, {menuIndex})");

			// function body
			this.Var_d4ca_MenuShortcutKey = -1;
			this.Var_654a = 0;

			MouseEvent mouseEvent = this.parent.GetMouseEvent();

			if (menuIndex == -1)
			{
				// Instruction address 0x2c84:0x0026, size: 5
				menuIndex = this.parent.Tools.F0_2dc4_007c_CheckValueRange(mouseEvent.Position.X / 60, 0, 4);
			}

			this.parent.Graphics.F0_VGA_07d8_DrawImage(this.parent.Var_aa_Screen0_Rectangle, 0, 0, 320, 200, this.parent.Var_19d4_Screen1_Rectangle, 0, 0);

			switch (menuIndex)
			{
				case 0:
					// Instruction address 0x2c84:0x005e, size: 3
					F0_2c84_00ad_GameMenu();
					break;

				case 1:
					// Instruction address 0x2c84:0x006a, size: 3
					F0_2c84_01d8_OrdersMenu(playerID, unitID);
					break;

				case 2:
					// Instruction address 0x2c84:0x0073, size: 3
					F0_2c84_0615_AdvisorsMenu();
					break;

				case 3:
					// Instruction address 0x2c84:0x0079, size: 3
					F0_2c84_06e4_ShowWorldMenu();
					break;

				case 4:
					// Instruction address 0x2c84:0x007f, size: 3
					F0_2c84_07af_EncyclopediaMenu();
					break;
			}

			if (this.Var_654a == 1)
			{
				// Instruction address 0x2c84:0x0094, size: 5
				this.parent.Segment_1238.F0_1238_1b44();
			}

			if (this.Var_654a == 0)
			{
				this.parent.Graphics.F0_VGA_07d8_DrawImage(this.parent.Var_19d4_Screen1_Rectangle, 0, 0, 320, 200, this.parent.Var_aa_Screen0_Rectangle, 0, 0);
			}
		}

		/// <summary>
		/// Shows game menu and handles its options sub menu
		/// </summary>
		private void F0_2c84_00ad_GameMenu()
		{
			//this.oCPU.Log.EnterBlock("F0_2c84_00ad_GameMenu()");

			// function body
			// Enable Save game with zero turns
			if (this.parent.GameData.TurnCount == 0)
			{
				// Disable 'Save Game' option
				//this.oParent.Var_b276_MenuBoxDisabledOptions = 0x10;
			}

			// Instruction address 0x2c84:0x00f4, size: 5
			bool usesSmartEnhancements =
				ClassicAiRuntimeProfiles.UsesSmartEnhancements(
					this.parent.GameData.AiProfile);
			int selectedOption = this.parent.MenuBoxDialog.F0_2d05_0031_ShowMenuBox(
				ClassicGameText.Current[
					usesSmartEnhancements
						? ClassicGameTextKey.GameMenu1991Plus
						: ClassicGameTextKey.GameMenu] +
				(((this.parent.GameData.SpaceshipFlags & 0x100) != 0)
					? ClassicGameText.Current[
						ClassicGameTextKey.GameMenuViewReplay]
					: ""),
				16, 8, true, false, false);

			// Instruction address 0x2c84:0x00ff, size: 5
			this.parent.CommonTools.ClearKeyboardAndMouseEvents();

			if (usesSmartEnhancements && selectedOption == 5)
			{
				this.Var_d4ca_MenuShortcutKey = 'L';
				return;
			}

			if (usesSmartEnhancements && selectedOption > 5)
			{
				selectedOption--;
			}

			switch (selectedOption)
			{
				case 0: // Tax Rate
					this.Var_d4ca_MenuShortcutKey = '=';
					break;

				case 1: // Luxuries
					this.Var_d4ca_MenuShortcutKey = '-';
					break;

				case 2: // Find City
					this.Var_d4ca_MenuShortcutKey = '?';
					break;

				case 3: // Options
						// Instruction address 0x2c84:0x0143, size: 5
					int index;

					do
					{
						// Write current flags to show as checkmarks in options submenu
						GameSettings settings =
							this.parent.GameData.GameSettingFlags;
						bool optionsUseSmartEnhancements =
							ClassicAiRuntimeProfiles
								.UsesSmartEnhancements(
									this.parent.GameData.AiProfile);
						bool anyQualityOfLifeOption =
							optionsUseSmartEnhancements &&
							settings.Has1991PlusOptionsEnabled();
						int standardOptions =
							settings.Value & 0x1ff;
						if (optionsUseSmartEnhancements)
						{
							// Original Civ1 stores this bit as "wait for an
							// end-of-turn confirmation". In 1991+ the same
							// saved choice is presented from the player's
							// perspective: checked means end the turn
							// automatically, so the check mark is inverted.
							standardOptions =
								(standardOptions & ~(1 << 2)) |
								(!settings.EndOfTurn ? 1 << 2 : 0);
						}
						this.parent.Var_d7f2_MenuBoxCheckedOptions =
							standardOptions |
							(anyQualityOfLifeOption ? 1 << 9 : 0);
						this.parent.Var_b276_MenuBoxDisabledOptions =
							optionsUseSmartEnhancements
								? 0
								: 1 << 9;
						// Process options submenu, return selected option index or -1 if selection was rejected
						index = this.parent.MenuBoxDialog.F0_2d05_0031_ShowMenuBox(
							ClassicGameText.Current[
								optionsUseSmartEnhancements
									? ClassicGameTextKey
										.GameOptionsMenu1991Plus
									: ClassicGameTextKey.GameOptionsMenu],
							24, 16, true, false, false);

						if (index == -1)
						{
							continue;
						}

						if (!this.parent.Var_2f9c_MenuBoxHelpRequested)
						{
							if (index == 4)
							{
								this.parent.CommonTools.SetSoundEnabled(
									!this.parent.GameData.GameSettingFlags.Sound);
							}
							else if (index == 9)
							{
								ShowQualityOfLifeMenu();
							}
							else
							{
								this.parent.GameData.GameSettingFlags.Value ^=
									(short)(1 << index);
							}
						}

						if (index != -1)
						{
							this.parent.Var_2f9a_MenuBoxDefaultOptionIndex = index;
						}
					}
					while (index != -1 || this.parent.Var_2f9c_MenuBoxHelpRequested);

					break;

				case 4:
					// Save Game
					this.Var_d4ca_MenuShortcutKey = 'S';
					break;

				case 5:
					// Revolution
					this.Var_d4ca_MenuShortcutKey = -2;
					break;

				case 6:
					// Empty option line
					break;

				case 7:
					// Retire
					this.parent.Var_dc48_GameEndType = 2;
					this.Var_d4ca_MenuShortcutKey = 0x1000;
					break;

				case 8:
					// Quit
					this.parent.Var_dc48_GameEndType = 1;
					this.Var_d4ca_MenuShortcutKey = 0x1000;
					break;

				case 9:
					// View replay
					this.parent.Replay.F9_0000_0000();
					break;
			}
		}

		private void ShowQualityOfLifeMenu()
		{
			if (!ClassicAiRuntimeProfiles.UsesSmartEnhancements(
					this.parent.GameData.AiProfile))
			{
				return;
			}

			int selectedOption;

			do
			{
				GameSettings settings =
					this.parent.GameData.GameSettingFlags;
				this.parent.Var_d7f2_MenuBoxCheckedOptions =
					(settings.AutomaticExplore ? 1 : 0) |
					(settings.ImproveNearestCity ? 1 << 1 : 0) |
					(settings.BuildRoadToCity ? 1 << 2 : 0) |
					(settings.AutomaticHomeCityReassignment
						? 1 << 3
						: 0) |
					(settings.ShowGoToPaths ? 1 << 4 : 0) |
					(settings.CaravanTradeAdvisor ? 1 << 5 : 0);

				selectedOption =
					this.parent.MenuBoxDialog.F0_2d05_0031_ShowMenuBox(
						ClassicGameText.Current[
							ClassicGameTextKey.QualityOfLifeMenu],
						32, 24, true, false, false);

				if (selectedOption < 0)
				{
					continue;
				}

				switch (selectedOption)
				{
					case 0:
						settings.AutomaticExplore =
							!settings.AutomaticExplore;
						if (!settings.AutomaticExplore)
						{
							this.parent.UnitAutomationState.CancelKind(
								ClassicUnitAutomationKind.AutomaticExplore);
						}
						break;
					case 1:
						settings.ImproveNearestCity =
							!settings.ImproveNearestCity;
						if (!settings.ImproveNearestCity)
						{
							this.parent.UnitAutomationState.CancelKind(
								ClassicUnitAutomationKind.ImproveNearestCity);
						}
						break;
					case 2:
						settings.BuildRoadToCity =
							!settings.BuildRoadToCity;
						if (!settings.BuildRoadToCity)
						{
							this.parent.UnitAutomationState.CancelKind(
								ClassicUnitAutomationKind.BuildRoadToCity);
						}
						break;
					case 3:
						settings.AutomaticHomeCityReassignment =
							!settings.AutomaticHomeCityReassignment;
						break;
					case 4:
						settings.ShowGoToPaths =
							!settings.ShowGoToPaths;
						this.goToPathOverlayRefreshRequested = true;
						break;
					case 5:
						settings.CaravanTradeAdvisor =
							!settings.CaravanTradeAdvisor;
						break;
				}

				this.parent.Var_2f9a_MenuBoxDefaultOptionIndex =
					selectedOption;
			}
			while (selectedOption != -1);
		}

		/// <summary>
		/// Shows orders menu
		/// </summary>
		/// <param name="playerID"></param>
		/// <param name="unitID"></param>
		private void F0_2c84_01d8_OrdersMenu(int playerID, int unitID)
		{
			//this.oCPU.Log.EnterBlock($"F0_2c84_01d8_OrdersMenu({playerID}, {unitID})");

			// function body
			if (unitID >= 0 && unitID < 128)
			{
				StringBuilder menuText = new();

				Unit unit = this.parent.GameData.Players[playerID].Units[unitID];

				// Instruction address 0x2c84:0x0221, size: 5
				TerrainImprovementFlagsEnum improvements = this.parent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(unit.Position.X, unit.Position.Y);

				// Instruction address 0x2c84:0x0232, size: 5
				TerrainTypeEnum terrainType = this.parent.MapManagement.GetTerrainType(unit.Position.X, unit.Position.Y);

				int orderCount = 0;
				char[] orders = new char[24];

				// Instruction address 0x2c84:0x0245, size: 5
				menuText.Append(
					ClassicGameText.Current.Format(
						ClassicGameTextKey.OrdersNoOrders,
						"\x008f"));
				orders[orderCount++] = ' ';

				// All orders are enabled by default
				this.parent.Var_b276_MenuBoxDisabledOptions = 0;

				if (unit.UnitType == UnitTypeEnum.Settler)
				{
					if (improvements.HasFlag(TerrainImprovementFlagsEnum.City))
					{
						// Instruction address 0x2c84:0x027a, size: 5
						menuText.Append(
							ClassicGameText.Current.Format(
								ClassicGameTextKey.OrdersAddToCity,
								"\x008f"));
					}
					else
					{
						// Instruction address 0x2c84:0x027a, size: 5
						menuText.Append(
							ClassicGameText.Current.Format(
								ClassicGameTextKey.OrdersFoundNewCity,
								"\x008f"));
					}

					orders[orderCount++] = 'b';

					if (!improvements.HasFlag(TerrainImprovementFlagsEnum.Road))
					{
						// Instruction address 0x2c84:0x029a, size: 5
						menuText.Append(
							ClassicGameText.Current.Format(
								ClassicGameTextKey.OrdersBuildRoad,
								"\x008f"));
						orders[orderCount++] = 'r';
					}
					else
					{
						// Instruction address 0x2c84:0x02bb, size: 5
						if (!improvements.HasFlag(TerrainImprovementFlagsEnum.RailRoad) && this.parent.Segment_1ade.F0_1ade_22b5_PlayerHasTechnology(playerID, TechnologyAdvanceEnum.Railroad))
						{
							// Instruction address 0x2c84:0x02cf, size: 5
							menuText.Append(
								ClassicGameText.Current.Format(
									ClassicGameTextKey.OrdersBuildRailroad,
									"\x008f"));
							orders[orderCount++] = 'r';
						}
					}

					if (!improvements.HasFlag(TerrainImprovementFlagsEnum.Irrigation))
					{
						if (this.parent.GameData.TerrainModifications[(int)terrainType].IrrigationEffect == -2)
						{
							// Instruction address 0x2c84:0x0301, size: 5
							menuText.Append(
								ClassicGameText.Current[
									ClassicGameTextKey.OrdersBuildIrrigation]);

							// Instruction address 0x2c84:0x030f, size: 5
							if (!this.parent.MapManagement.CanIrrigateCell(unit.Position.X, unit.Position.Y))
							{
								// Disable 'Build Irrigation' option
								this.parent.Var_b276_MenuBoxDisabledOptions |= 0x1 << orderCount;
							}
						}
						else
						{
							if (this.parent.GameData.TerrainModifications[(int)terrainType].IrrigationEffect >= 0)
							{
								// Instruction address 0x2c84:0x0342, size: 5
								menuText.Append(
									ClassicGameText.Current[
										ClassicGameTextKey.OrdersChangeToPrefix]);

								// Instruction address 0x2c84:0x035d, size: 5
								TerrainTypeEnum changedTerrain =
									this.parent.PixelValuesToTerrainTypes[
										this.parent.GameData.TerrainModifications[
											(int)terrainType].IrrigationEffect];
								menuText.Append(
									ClassicDisplayNames.Terrain(
										changedTerrain,
										this.parent.GameData.Terrains[
											(int)changedTerrain].Name));
							}
						}

						if (this.parent.GameData.TerrainModifications[(int)terrainType].IrrigationEffect != -1)
						{
							// Instruction address 0x2c84:0x0386, size: 5
							menuText.Append(" \x008fi\n");
							orders[orderCount++] = 'i';
						}
					}

					if (!improvements.HasFlag(TerrainImprovementFlagsEnum.Mines))
					{
						if (this.parent.GameData.TerrainModifications[(int)terrainType].MiningEffect <= -2)
						{
							// Instruction address 0x2c84:0x03dc, size: 5
							menuText.Append(
								ClassicGameText.Current[
									ClassicGameTextKey.OrdersBuildMines]);
						}
						else if (this.parent.GameData.TerrainModifications[(int)terrainType].MiningEffect >= 0)
						{
							// Instruction address 0x2c84:0x03c1, size: 5
							menuText.Append(
								ClassicGameText.Current[
									ClassicGameTextKey.OrdersChangeToPrefix]);

							// Instruction address 0x2c84:0x03dc, size: 5
							TerrainTypeEnum changedTerrain =
								this.parent.PixelValuesToTerrainTypes[
									this.parent.GameData.TerrainModifications[
										(int)terrainType].MiningEffect];
							menuText.Append(
								ClassicDisplayNames.Terrain(
									changedTerrain,
									this.parent.GameData.Terrains[
										(int)changedTerrain].Name));
						}

						if (this.parent.GameData.TerrainModifications[(int)terrainType].MiningEffect != -1)
						{
							// Instruction address 0x2c84:0x0405, size: 5
							menuText.Append(" \x008fm\n");
							orders[orderCount++] = 'm';
						}
					}

					if (improvements.HasFlag(TerrainImprovementFlagsEnum.Pollution))
					{
						// Instruction address 0x2c84:0x041b, size: 5
						menuText.Append(
							ClassicGameText.Current.Format(
								ClassicGameTextKey.OrdersCleanPollution,
								"\x008f"));
						orders[orderCount++] = 'p';
					}
				}

				if (unit.UnitType == UnitTypeEnum.Settler)
				{
					// Instruction address 0x2c84:0x044c, size: 5
					menuText.Append(
						ClassicGameText.Current.Format(
							ClassicGameTextKey.OrdersBuildFortress,
							"\x008f"));

					// Instruction address 0x2c84:0x045b, size: 5
					if (!this.parent.Segment_1ade.F0_1ade_22b5_PlayerHasTechnology(playerID, TechnologyAdvanceEnum.Construction))
					{
						// Disable 'Build Fortress' option
						this.parent.Var_b276_MenuBoxDisabledOptions |= 0x1 << orderCount;
					}
					orders[orderCount++] = 'f';
				}
				else if (this.parent.GameData.Units[(int)unit.UnitType].MovementType == UnitMovementTypeEnum.Land)
				{
					// Instruction address 0x2c84:0x049c, size: 5
					menuText.Append(
						ClassicGameText.Current.Format(
							ClassicGameTextKey.OrdersFortify,
							"\x008f"));
					orders[orderCount++] = 'f';
				}

				// Instruction address 0x2c84:0x04d5, size: 5
				menuText.Append(
					ClassicGameText.Current.Format(
						ClassicGameTextKey.OrdersWaitSentryGoTo,
						"\x008f"));

				orders[orderCount++] = 'w';
				orders[orderCount++] = 's';
				orders[orderCount++] = 'g';

				UnitMovementTypeEnum movementType =
					this.parent.GameData.Units[
						(int)unit.UnitType].MovementType;
				bool usesSmartEnhancements =
					ClassicAiRuntimeProfiles.UsesSmartEnhancements(
						this.parent.GameData.AiProfile);
				if (usesSmartEnhancements &&
					this.parent.GameData.GameSettingFlags.AutomaticExplore &&
					playerID == this.parent.GameData.HumanPlayerID &&
					unit.RemainingMoves > 0 &&
					unit.UnitType != UnitTypeEnum.Nuclear &&
					(movementType == UnitMovementTypeEnum.Land ||
					 movementType == UnitMovementTypeEnum.Water))
				{
					menuText.Append(
						ClassicGameText.Current.Format(
							ClassicGameTextKey.OrdersAutomaticExplore,
							"\x008f"));
					orders[orderCount++] = 'e';
				}

				if (usesSmartEnhancements &&
					this.parent.GameData.GameSettingFlags
						.ImproveNearestCity &&
					playerID == this.parent.GameData.HumanPlayerID &&
					unit.RemainingMoves > 0 &&
					unit.UnitType == UnitTypeEnum.Settler)
				{
					menuText.Append(
						ClassicGameText.Current.Format(
							ClassicGameTextKey
								.OrdersImproveNearestCity,
							"\x008f"));
					orders[orderCount++] = 'v';
				}

				if (usesSmartEnhancements &&
					this.parent.GameData.GameSettingFlags
						.BuildRoadToCity &&
					playerID == this.parent.GameData.HumanPlayerID &&
					unit.RemainingMoves > 0 &&
					unit.UnitType == UnitTypeEnum.Settler)
				{
					menuText.Append(
						ClassicGameText.Current.Format(
							ClassicGameTextKey.OrdersRoadToCity,
							"\x008f"));
					orders[orderCount++] = 'x';
				}

				if (usesSmartEnhancements &&
					this.parent.GameData.GameSettingFlags
						.CaravanTradeAdvisor &&
					playerID == this.parent.GameData.HumanPlayerID &&
					unit.UnitType == UnitTypeEnum.Caravan)
				{
					menuText.Append(
						ClassicGameText.Current.Format(
							ClassicGameTextKey
								.OrdersSuggestTradeDestination,
							"\x008f"));
					orders[orderCount++] = 'T';
				}

				if (((ushort)improvements & (ushort)TerrainImprovementFlagsEnum.PillageMask) != 0 && 
					(unit.UnitType != UnitTypeEnum.Diplomat && unit.UnitType != UnitTypeEnum.Caravan) && 
					unit.UnitType != UnitTypeEnum.Fighter)
				{
					// Instruction address 0x2c84:0x0528, size: 5
					menuText.Append(
						ClassicGameText.Current.Format(
							ClassicGameTextKey.OrdersPillage,
							"\x008f"));
					orders[orderCount++] = 'P';
				}

				if (improvements.HasFlag(TerrainImprovementFlagsEnum.City))
				{
					// Instruction address 0x2c84:0x0548, size: 5
					menuText.Append(
						ClassicGameText.Current.Format(
							ClassicGameTextKey.OrdersHomeCity,
							"\x008f"));
					orders[orderCount++] = 'h';
				}

				// Instruction address 0x2c84:0x05a4, size: 5
				if ((this.parent.GameData.Units[(int)unit.UnitType].UnitRoleType == UnitRoleTypeEnum.SeaTransport || unit.UnitType == UnitTypeEnum.Carrier) && unit.NextUnitID != -1)
				{
					// Instruction address 0x2c84:0x05a4, size: 5
					menuText.Append(
						ClassicGameText.Current.Format(
							ClassicGameTextKey.OrdersUnload,
							"\x008f"));
					orders[orderCount++] = 'u';
				}

				if (usesSmartEnhancements &&
					playerID ==
						this.parent.GameData.HumanPlayerID)
				{
					menuText.Append(
						ClassicGameText.Current.Format(
							ClassicGameTextKey.OrdersWakeAllOfType,
							ClassicDisplayNames.Unit(
								unit.UnitType,
								this.parent.GameData.Units[
									(int)unit.UnitType].Name),
							"\x008f"));
					orders[orderCount++] = 'W';
				}

				// Instruction address 0x2c84:0x05be, size: 5
				menuText.Append(
					ClassicGameText.Current.Format(
						ClassicGameTextKey.OrdersDisbandUnit,
						"\x008f"));

				// Empty option line does not use hotkey
				orders[orderCount++] = '\0';
				orders[orderCount++] = 'D';

				// Instruction address 0x2c84:0x05e6, size: 5
				int selectedOrder = this.parent.MenuBoxDialog.F0_2d05_0031_ShowMenuBox(menuText.ToString(), 72, 8, true, false, false);

				if (selectedOrder < 0 || selectedOrder >= orderCount)
				{
					this.Var_d4ca_MenuShortcutKey = -1;
				}
				else
				{
					this.Var_d4ca_MenuShortcutKey = orders[selectedOrder];
				}
			}
		}

		/// <summary>
		/// Shows advisors menu
		/// </summary>
		private void F0_2c84_0615_AdvisorsMenu()
		{
			//this.oCPU.Log.EnterBlock("F0_2c84_0615_AdvisorsMenu()");

			// function body
			// Instruction address 0x2c84:0x0647, size: 5
			int selectedOption = this.parent.MenuBoxDialog.F0_2d05_0031_ShowMenuBox(
				ClassicGameText.Current[ClassicGameTextKey.AdvisorsMenu],
				112, 8, true, false, false);

			this.parent.Graphics.F0_VGA_07d8_DrawImage(this.parent.Var_19d4_Screen1_Rectangle, 0, 0, 320, 200, this.parent.Var_aa_Screen0_Rectangle, 0, 0);

			Var_654a = -1;

			switch (selectedOption)
			{
				case 0: // City Status
					this.parent.Overlay_14.F14_0000_186f_CityStatus(this.parent.GameData.HumanPlayerID);
					break;

				case 1: // Military Advisor
					this.parent.Overlay_14.F14_0000_03ad_MilitaryReport(this.parent.GameData.HumanPlayerID);
					break;

				case 2: // Intelligence Advisor
					this.parent.Overlay_14.F14_0000_0d43_IntelligenceReport();
					break;

				case 3: // Attitude Advisor
					this.parent.Overlay_14.F14_0000_15f4_AttitudeReport(this.parent.GameData.HumanPlayerID);
					break;

				case 4: // Trade Advisor
					this.parent.Overlay_14.F14_0000_07f1_TradeReport(this.parent.GameData.HumanPlayerID);
					break;

				case 5: // Science Advisor
					this.parent.Overlay_14.F14_0000_014b_ScienceReport(this.parent.GameData.HumanPlayerID);
					break;
			}
		}

		/// <summary>
		/// Shows world menu
		/// </summary>
		private void F0_2c84_06e4_ShowWorldMenu()
		{
			//this.oCPU.Log.EnterBlock("F0_2c84_06e4_ShowWorldMenu()");

			// function body
			if ((this.parent.GameData.SpaceshipFlags & 0xfe00) == 0)
			{
				// Disable 'SpaceShips' option
				this.parent.Var_b276_MenuBoxDisabledOptions = 0x20;
			}

			// Instruction address 0x2c84:0x0724, size: 5
			int selectedOption = this.parent.MenuBoxDialog.F0_2d05_0031_ShowMenuBox(
				ClassicGameText.Current[ClassicGameTextKey.WorldMenu],
				144, 8, true, false, false);

			this.parent.Graphics.F0_VGA_07d8_DrawImage(this.parent.Var_19d4_Screen1_Rectangle, 0, 0, 320, 200, this.parent.Var_aa_Screen0_Rectangle, 0, 0);

			this.Var_654a = -1;

			switch (selectedOption)
			{
				case 0: // Wonders of the World
					this.parent.Reports.F12_0000_080d_ShowWondersOfTheWorldReport();
					break;

				case 1: // Top 5 Cities
					this.parent.HallOfFame.F3_0000_09ac_ShowTopFiveCitiesPopup();
					break;

				case 2: // Civilization Score
					this.parent.Overlay_20.F20_0000_0ca9_ShowCivilizationScorePopup(this.parent.GameData.HumanPlayerID, true);
					break;

				case 3: // World Map
					this.parent.Reports.F12_0000_0000_ShowWorldMapReport();
					break;

				case 4: // Demographics
					this.parent.Reports.F12_0000_0d6d_ShowsDemographicsReport(this.parent.GameData.HumanPlayerID);
					break;

				case 5: // SpaceShips
					this.parent.Overlay_18.F18_0000_1527_ShowSpaceshipNationDialog();
					break;
			}
		}

		/// <summary>
		/// Shows Encyclopedia menu
		/// </summary>
		private void F0_2c84_07af_EncyclopediaMenu()
		{
			//this.oCPU.Log.EnterBlock("F0_2c84_07af_EncyclopediaMenu()");

			// function body
			// Instruction address 0x2c84:0x07e1, size: 5
			int selectedOption = this.parent.MenuBoxDialog.F0_2d05_0031_ShowMenuBox(
				ClassicGameText.Current[ClassicGameTextKey.EncyclopediaMenu],
				182, 8, true, false, false);

			if (selectedOption < 0)
			{
				this.Var_654a = 1;
			}
			else
			{
				this.parent.Encyclopedia.F8_0000_0000_ShowEncyclopediaByTopic((EncyclopediaTopicEnum)selectedOption);
				this.Var_654a = -1;
			}
		}
	}
}
