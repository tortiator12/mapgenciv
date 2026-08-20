using IRB.VirtualCPU;
using OpenCivOne.Graphics;
using OpenCivOne.Localization;
using OpenCivOne.Platform;
using OpenCivOne.Runtime;
using System.Diagnostics;
using System.Text;

namespace OpenCivOne
{
	public class PlayerTurn
	{
		private const int CarrierAircraftCapacity = 8;
		private OpenCivOneGame parent;
		private bool UsesSmartEnhancements =>
			ClassicAiRuntimeProfiles.UsesSmartEnhancements(
				this.parent.GameData.AiProfile);

		private bool ShouldWaitForEndOfTurnConfirmation(
			bool receivedUnitInput)
		{
			// Original 1991 also shows the prompt when no ordinary unit input
			// occurred during the turn. Preserve that source-faithful branch.
			// In 1991+ the explicit option is authoritative, which lets fully
			// automated or already-finished turns advance without Enter.
			return this.UsesSmartEnhancements
				? this.parent.GameData.GameSettingFlags.EndOfTurn ||
					this.parent
						.ConsumeAutomaticEndTurnPauseRequest()
				: !receivedUnitInput ||
					this.parent.GameData.GameSettingFlags.EndOfTurn;
		}

		private sealed record AutomaticExploreObservation(
			GPoint Position,
			int KnownCellCount);

		private sealed record AutomaticExploreProgress(
			Unit Unit,
			GPoint PreviousPosition,
			GPoint CurrentPosition,
			bool RevealedNewCells);

		private readonly Dictionary<(int PlayerID, int UnitID),
			AutomaticExploreProgress> automaticExploreProgress = [];

		public PlayerTurn(OpenCivOneGame parent)
		{
			this.parent = parent;
		}

		internal static string BuildRateMenuPrefix(
			string title,
			string? forecast)
		{
			ArgumentNullException.ThrowIfNull(title);
			return string.IsNullOrEmpty(forecast)
				? $"{title}\n "
				: $"{title}\n{forecast}\n ";
		}

		private string Get1991PlusEconomyForecastLine(
			int playerID)
		{
			if (!this.UsesSmartEnhancements)
			{
				return string.Empty;
			}

			ClassicPlayerIntelligenceSnapshot forecast =
				ClassicCityIntelligence.MeasurePlayer(
					this.parent,
					playerID);
			string researchTurns =
				forecast.ResearchTurns.HasValue
					? ClassicGameText.Current.Format(
						ClassicGameTextKey
							.CityQolProductionTurns,
						forecast.ResearchTurns.Value)
					: ClassicGameText.Current[
						ClassicGameTextKey.QolNoEta];
			return ClassicGameText.Current.Format(
				ClassicGameTextKey
					.EconomyQolCurrentForecast,
				forecast.NetGoldPerTurn > 0
					? $"+{forecast.NetGoldPerTurn}"
					: forecast.NetGoldPerTurn.ToString(),
				researchTurns);
		}

		private void ShowCaravanTradeAdvisor(
			int playerID,
			int unitID)
		{
			string title = ClassicGameText.Current[
				ClassicGameTextKey.CaravanTradeAdvisorTitle];
			if (!ClassicCaravanTradeAdvisor.TryRecommend(
					this.parent,
					playerID,
					unitID,
					out ClassicCaravanTradeRecommendation recommendation))
			{
				this.parent.Host.ShowInformation(
					ClassicGameText.Current[
						ClassicGameTextKey
							.CaravanTradeAdvisorNoKnownDestination],
					title);
				return;
			}

			string cityName =
				this.parent.Segment_2459
					.F0_2459_08c6_GetCityName(
						recommendation.CityID);
			string route =
				recommendation.HasKnownLandRoute
					? ClassicGameText.Current.Format(
						ClassicGameTextKey
							.CaravanTradeAdvisorKnownLandRoute,
						recommendation.KnownLandRouteSteps ?? 0)
					: ClassicGameText.Current[
						ClassicGameTextKey
							.CaravanTradeAdvisorTransportRequired];
			string routeStatus =
				ClassicGameText.Current[
					recommendation.IsExistingTradeRoute
						? ClassicGameTextKey
							.CaravanTradeAdvisorExistingRoute
						: ClassicGameTextKey
							.CaravanTradeAdvisorNewRoute];
			string message =
				recommendation.IsExact
					? ClassicGameText.Current.Format(
						ClassicGameTextKey
							.CaravanTradeAdvisorExactResult,
						cityName,
						recommendation.Payout ?? 0,
						recommendation.TradeBonus ?? 0,
						route,
						routeStatus)
					: ClassicGameText.Current.Format(
						ClassicGameTextKey
							.CaravanTradeAdvisorApproximateResult,
						cityName,
						recommendation.VisibleSize,
						route,
						routeStatus);
			this.parent.Host.ShowInformation(message, title);
		}

		/// <summary>
		/// This function handles given Player turn. All unit movements, keyboard and mouse events
		/// </summary>
		/// <param name="playerID"></param>
		public void F0_1403_000e_PlayerTurn(int playerID)
		{
			using OpenCivOne.Presentation
				.ClassicRuntimePresentationState
				.ClassicRuntimeMutationLease presentationLease =
					this.parent.PresentationState
						.EnterRuntimeMutation();
			//this.oCPU.Log.EnterBlock("'Fn1'(Cdecl, Far, Return) at 0xe");
			// Local variables
			GPoint direction;

			// function body
			this.parent.Var_6b90_CurrentPlayer = playerID;

			if (playerID == this.parent.GameData.HumanPlayerID)
			{
				this.parent.ActiveHumanGoToPathUnitID = -1;
				ClearHumanGoToHoverPreview(
					presentationLease,
					playerID,
					refresh: false);
				this.parent.GameData.PlayerFlags = (short)(0x1 << this.parent.GameData.HumanPlayerID);

				if (this.parent.GameData.TurnCount == 20 || this.parent.GameData.TurnCount == 60)
				{
					ShowWorldMapOverlayWithPresentation(
						presentationLease,
						playerID,
						-1,
						() => this.parent.Help.F4_0000_02d3_ShowInstantAdvicePopup("*HELP1"));
				}

				if (this.parent.GameData.TurnCount == 40 || this.parent.GameData.TurnCount == 80)
				{
					ShowWorldMapOverlayWithPresentation(
						presentationLease,
						playerID,
						-1,
						() => this.parent.Help.F4_0000_02d3_ShowInstantAdvicePopup("*HELP2"));
				}
			}

			for (int i = 0; i < 128; i++)
			{
				if (this.parent.GameData.Players[playerID].Units[i].UnitType != UnitTypeEnum.None && this.parent.Var_df60 != 1)
				{
					if (playerID != this.parent.GameData.HumanPlayerID &&
						this.parent.GameData.Players[playerID].Units[i].UnitType ==
							UnitTypeEnum.Caravan)
					{
						this.parent.AIEngine.TrySettleClassicAiCaravan(
							playerID,
							i);
						continue;
					}

					this.parent.GameData.Players[playerID].Units[i].RemainingMoves =
						(short)(this.parent.GameData.Units[(int)this.parent.GameData.Players[playerID].Units[i].UnitType].MoveCount * 3);

					if (this.parent.GameData.Units[(int)this.parent.GameData.Players[playerID].Units[i].UnitType].MovementType == UnitMovementTypeEnum.Water)
					{
						if (this.parent.CityWorker.F0_1d12_6c97_PlayerHasWonder(playerID, WonderEnum.Lighthouse) ||
							this.parent.CityWorker.F0_1d12_6c97_PlayerHasWonder(playerID, WonderEnum.MagellansExpedition))
						{
							this.parent.GameData.Players[playerID].Units[i].RemainingMoves += 3;
						}
					}
				}
			}

			int command;
			int maxUnitID = 127;
			bool flag2 = true;
			bool flag3 = false;
			bool flag4 = false;
			bool flag5 = false;
			bool flag6 = false;
			bool flag7 = false;
			bool[] fuelProcessedThisTurn = new bool[128];
			bool automaticExploreMove = false;
			bool automaticExploreInterruptedByManualInput = false;
			bool selectingRoadToCityTarget = false;
			bool spentManualSelectionQolOnly = false;
			bool preserveSmartAiTransportGoToWait = false;
			AutomaticExploreObservation? automaticExploreObservation =
				null;

		Label17:
			int unitID = 0;
			flag2 = true;
			goto Label19;

		Label18:
			unitID++;

		Label19:
			if (unitID > 127) goto Label748;

			if (this.parent.Var_1ae0 != 0)
			{
				// Instruction address 0x1403:0x0160, size: 5
				this.parent.Segment_1238.F0_1238_1b44();
			}

			if (this.parent.Var_dc48_GameEndType != 0)
			{
				unitID = 128;
				goto Label18;
			}

			if (unitID == maxUnitID)
			{
				flag4 = true;
			}

			if (this.parent.GameData.Players[playerID].Units[unitID].UnitType == UnitTypeEnum.None) goto Label18;

			this.parent.GameTurnStageForTests?.Invoke(
				$"player-turn:{playerID}:unit:{unitID}:begin:" +
				$"type:{this.parent.GameData.Players[playerID].Units[unitID].UnitType}:" +
				$"pos:{this.parent.GameData.Players[playerID].Units[unitID].Position.X}," +
				$"{this.parent.GameData.Players[playerID].Units[unitID].Position.Y}:" +
				$"moves:{this.parent.GameData.Players[playerID].Units[unitID].RemainingMoves}");

			if ((int)this.parent.GameData.Players[playerID].Units[unitID].UnitType > 27)
			{
				throw new Exception($"The unit has invalid UnitType of {(int)this.parent.GameData.Players[playerID].Units[unitID].UnitType}, " +
					$"unitID: {unitID}, player {this.parent.GameData.Players[playerID].Name}");

				//this.parent.GameData.Players[playerID].Units[unitID].UnitType = UnitTypeEnum.Militia;
			}

			if (!flag6)
			{
				// Instruction address 0x1403:0x01f4, size: 5
				this.parent.UnitManagement.F0_1866_01dc(
					this.parent.GameData.Players[playerID].Units[unitID].Position.X,
					this.parent.GameData.Players[playerID].Units[unitID].Position.Y,
					playerID, unitID, false);
			}

			if ((this.parent.GameData.Players[playerID].Units[unitID].Status & (UnitStatusEnum.Sentry | UnitStatusEnum.Fortified)) != UnitStatusEnum.None ||
				this.parent.GameData.Players[playerID].Units[unitID].RemainingMoves == 0) goto Label18;

			if ((this.parent.GameData.Players[playerID].Units[unitID].Status & UnitStatusEnum.Fortifying) != UnitStatusEnum.None)
			{
				this.parent.GameData.Players[playerID].Units[unitID].ClearStatusFlags(UnitStatusEnum.Fortifying);
				this.parent.GameData.Players[playerID].Units[unitID].Status |= UnitStatusEnum.Fortified;
				this.parent.GameData.Players[playerID].Units[unitID].RemainingMoves = 0;

				// Instruction address 0x1403:0x0265, size: 5
				F0_1403_3f13_RedrawUnit(playerID, unitID);

				if (playerID != this.parent.GameData.HumanPlayerID)
				{
					if (this.parent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(this.parent.GameData.Players[playerID].Units[unitID].Position.X,
						this.parent.GameData.Players[playerID].Units[unitID].Position.Y).HasFlag(TerrainImprovementFlagsEnum.City))
					{
						int cityID = this.parent.Tools.F0_2dc4_00ba_GetCityByLocation(this.parent.GameData.Players[playerID].Units[unitID].Position.X,
							this.parent.GameData.Players[playerID].Units[unitID].Position.Y);

						if (this.parent.GameData.Cities[cityID].ActualSize >= 3)
						{
							this.parent.GameData.Players[playerID].Units[unitID].HomeCityID = (short)cityID;
						}
					}
				}

				if (this.parent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(this.parent.GameData.Players[playerID].Units[unitID].Position.X,
					this.parent.GameData.Players[playerID].Units[unitID].Position.Y).HasFlag(TerrainImprovementFlagsEnum.City))
				{
					int cityID = this.parent.Tools.F0_2dc4_00ba_GetCityByLocation(this.parent.GameData.Players[playerID].Units[unitID].Position.X,
						this.parent.GameData.Players[playerID].Units[unitID].Position.Y);

					if (this.parent.GameData.Players[playerID].Units[unitID].HomeCityID == cityID)
					{
						if (!this.parent.UnitManagement.F0_1866_18d0_IsEnemyUnitNear(playerID, this.parent.GameData.Players[playerID].Units[unitID].Position.X,
							this.parent.GameData.Players[playerID].Units[unitID].Position.Y))
						{
							this.parent.UnitManagement.F0_1866_00c6(cityID);
						}
					}
				}
				goto Label18;
			}

			if (playerID == this.parent.GameData.HumanPlayerID)
			{
				if ((this.parent.GameData.Players[playerID].Units[unitID].Status &
					(UnitStatusEnum.SettlerBuildRoadOrRail | UnitStatusEnum.SettlerBuildIrrigation | UnitStatusEnum.SettlerBuildMineOrForest)) == UnitStatusEnum.None)
				{
					if (this.parent.GameData.Players[playerID].Units[unitID].Position.X <= this.parent.Var_d4cc_MapViewX ||
						this.parent.GameData.Players[playerID].Units[unitID].Position.X >= this.parent.Var_d4cc_MapViewX + 14 ||
						this.parent.GameData.Players[playerID].Units[unitID].Position.Y <= this.parent.Var_d75e_MapViewY ||
						this.parent.GameData.Players[playerID].Units[unitID].Position.Y >= this.parent.Var_d75e_MapViewY + 10)
					{
						if (!flag4)
						{
							flag2 = false;
						}
						else
						{
							// Instruction address 0x1403:0x03dd, size: 5
							this.parent.CommonTools.WaitTimer(30);

							DrawVisibleMapWithPresentation(
								presentationLease,
								playerID,
								unitID,
								this.parent.GameData.Players[playerID].Units[unitID].Position.X - 7,
								this.parent.GameData.Players[playerID].Units[unitID].Position.Y - 6);

							maxUnitID = unitID - 1;
							if (maxUnitID < 0)
								maxUnitID = 127;

							flag4 = false;

							if (this.parent.GameData.TurnCount == 0)
							{
								F0_1403_4060(playerID, unitID);
							}

							goto Label54;
						}

						goto Label18;
					}
				}
			}

		Label54:
			spentManualSelectionQolOnly = false;
			if ((this.parent.GameData.PlayerFlags & (0x1 << playerID)) != 0)
			{
				// Instruction address 0x1403:0x044c, size: 5
				this.parent.CommonTools.ClearKeyboardAndMouseEvents();
			}

			int unitMoveCount = 0;

			if (flag3)
			{
				// Instruction address 0x1403:0x046b, size: 5
				this.parent.CommonTools.SetMousePositionAndIcon(0, 0, this.parent.Array_d4ce[7]);
			}

			flag3 = false;
			flag7 = false;

		Label59:
			automaticExploreMove = false;
			automaticExploreInterruptedByManualInput = false;
			automaticExploreObservation = null;
			preserveSmartAiTransportGoToWait = false;

			if ((this.parent.GameData.PlayerFlags & (0x1 << playerID)) == 0)
			{
				// Instruction address 0x1403:0x0496, size: 5
				this.parent.GameTurnStageForTests?.Invoke(
					$"player-turn:{playerID}:unit:{unitID}:ai-command-begin");
				command = this.parent.AIEngine.F0_25fb_0c9d_MoveUnit(playerID, unitID);
				this.parent.GameTurnStageForTests?.Invoke(
					$"player-turn:{playerID}:unit:{unitID}:ai-command-complete:" +
					$"command:{command}");
				preserveSmartAiTransportGoToWait =
					ShouldPreserveSmartAiTransportGoToWait(
						playerID,
						unitID,
						command);
				if (UsesSmartEnhancements &&
					command == 'u' &&
					this.parent.GameData.Units[
						(int)this.parent.GameData.Players[playerID]
							.Units[unitID].UnitType].UnitRoleType ==
						UnitRoleTypeEnum.SeaTransport)
				{
					// A deliberate Smart expedition unload must win over a
					// stale route left from the crossing. Otherwise Label151
					// replaces 'u' with the next Go To step and the ship
					// sails away from a valid landing coast.
					ClearUnitGoTo(
						this.parent.GameData.Players[playerID]
							.Units[unitID]);
				}

				if (command != 0 &&
					!preserveSmartAiTransportGoToWait)
				{
					this.parent.GameData.Players[playerID].Units[unitID].GoToDestination = OpenCivOneGame.InvalidPosition;
				}

				unitMoveCount++;

				if (unitMoveCount > 4)
				{
					command = ' ';
					this.parent.GameData.Players[playerID].Units[unitID].GoToDestination = OpenCivOneGame.InvalidPosition;
					this.parent.GameData.Players[playerID].Units[unitID].GoToNextDirection = -1;
				}

				goto Label151;
			}

			if (unitID >= 128)
			{
				goto Label79;
			}

			if (playerID == this.parent.GameData.HumanPlayerID)
			{
				// A continued Go To skips the manual-input label. Remember the
				// active unit here so its route remains visible next turn.
				this.parent.ActiveHumanGoToPathUnitID = unitID;
			}

			if (TryInterruptUnitAutomationForPendingManualInput(
				playerID,
				unitID,
				out ClassicUnitAutomationKind interruptedKind))
			{
				automaticExploreInterruptedByManualInput =
					interruptedKind ==
						ClassicUnitAutomationKind.AutomaticExplore;
				goto Label79;
			}

			bool hasOriginalContinuation =
				(this.parent.GameData.Players[playerID].Units[unitID].Status &
					(UnitStatusEnum.SettlerBuildRoadOrRail |
					 UnitStatusEnum.SettlerBuildIrrigation |
					 UnitStatusEnum.SettlerBuildMineOrForest)) !=
					UnitStatusEnum.None ||
				this.parent.GameData.Players[playerID]
					.Units[unitID].GoToDestination.X != -1;
			if (!hasOriginalContinuation)
			{
				if (TryPrepareRoadToCityAction(
					presentationLease,
					playerID,
					unitID,
					startRequested: false,
					destinationCityID: null,
					out command))
				{
					goto Label151;
				}

				if (TryPrepareImproveNearestCityAction(
					presentationLease,
					playerID,
					unitID,
					startRequested: false,
					out command))
				{
					goto Label151;
				}

				if (TryPrepareAutomaticExploreMove(
					playerID,
					unitID,
					out command,
					out automaticExploreObservation))
				{
					automaticExploreMove = true;
					goto Label151;
				}

				goto Label79;
			}

			if (this.parent.UnitAutomationState.TryGetOrder(
				this.parent.GameData,
				playerID,
				unitID,
				ClassicUnitAutomationKind.AutomaticExplore,
				out _))
			{
				this.parent.UnitAutomationState.Cancel(playerID, unitID);
			}

			command = 'r';

			if ((this.parent.GameData.Players[playerID].Units[unitID].Status & UnitStatusEnum.SettlerBuildIrrigation) != UnitStatusEnum.None)
			{
				if (this.parent.GameData.Players[playerID].Units[unitID].UnitType != UnitTypeEnum.Settler)
				{
					command = 'm';
				}
				else
				{
					command = 'i';
				}
			}

			if ((this.parent.GameData.Players[playerID].Units[unitID].Status & UnitStatusEnum.SettlerBuildMineOrForest) != UnitStatusEnum.None)
			{
				command = 'm';

				if ((this.parent.GameData.Players[playerID].Units[unitID].Status & UnitStatusEnum.SettlerBuildIrrigation) != UnitStatusEnum.None)
				{
					command = 'f';
				}

				if ((this.parent.GameData.Players[playerID].Units[unitID].Status & UnitStatusEnum.SettlerBuildRoadOrRail) != UnitStatusEnum.None)
				{
					command = 'p';
				}
			}

			if (this.parent.GameData.Units[(int)this.parent.GameData.Players[playerID].Units[unitID].UnitType].MovementType == UnitMovementTypeEnum.Air)
			{
				command = 'h';
			}
			goto Label151;

		Label79:
			SetActiveHumanGoToPathUnit(presentationLease, playerID, unitID);

			// Instruction address 0x1403:0x05d2, size: 5
			F0_1403_4060(playerID, unitID);

			if (this.parent.GameData.TurnCount == 0)
			{
				if (!flag6)
				{
					this.parent.Array_30b8[0] = this.parent.GameData.Players[playerID].Nation;
					ShowWorldMapOverlayWithPresentation(
						presentationLease,
						playerID,
						unitID,
						() => this.parent.Help.F4_0000_02d3_ShowInstantAdvicePopup("*FIRSTMOVE"));

					flag6 = true;
				}
			}

			if (unitID < 128 && this.parent.GameData.Players[playerID].Units[unitID].UnitType == UnitTypeEnum.Settler)
			{
				if (!flag6)
				{
					ShowWorldMapOverlayWithPresentation(
						presentationLease,
						playerID,
						unitID,
						() => this.parent.Help.F4_0000_00af_ShowInstantAdvicePopup(playerID, unitID));

					flag6 = true;
				}
			}

			presentationLease.PublishInteractiveAndRelease(
				playerID,
				unitID < 128 ? unitID : -1,
				isEndOfTurnPrompt: unitID >= 128);
			try
			{
				this.parent.InteractiveWorldMapWaitingForInputForTests?.Invoke(
					playerID,
					unitID);
				this.parent.UnitCommandWaitingForInputForTests?.Invoke(
					playerID,
					unitID);
				this.parent.UnitManagement.F0_1866_0ad6_ShowActiveUnitOrEndOfTurn(playerID, unitID, -1, 0);
			}
			finally
			{
				presentationLease.ReacquireAndMarkUnknown();
			}

			if (unitID < 128)
			{
				flag5 = true;
			}

			MouseEvent mouseEvent = this.parent.GetMouseEvent();
			command = -1;

			if (flag3 &&
				!selectingRoadToCityTarget &&
				unitID < 128)
			{
				UpdateHumanGoToHoverPreview(
					presentationLease,
					playerID,
					unitID,
					mouseEvent.Position);
			}
			else
			{
				ClearHumanGoToHoverPreview(
					presentationLease,
					playerID,
					refresh: true);
			}

			if (mouseEvent.Buttons == MouseButtonsEnum.None && this.parent.CAPI.kbhit() == 0) goto Label79;

			if (mouseEvent.Buttons == MouseButtonsEnum.None && this.parent.CAPI.kbhit() != 0)
			{
				// Instruction address 0x1403:0x0676, size: 5
				command = this.parent.MenuBoxDialog.F0_2d05_0ac9_GetNavigationKey();

				goto Label151;
			}

			int mouseX = this.parent.MapManagement.AdjustXPosition(((mouseEvent.Position.X - 80) / 16) + this.parent.Var_d4cc_MapViewX);
			int mouseY = ((mouseEvent.Position.Y - 8) / 16) + this.parent.Var_d75e_MapViewY;

			if (mouseEvent.Position.Y < 8)
			{
				// Instruction address 0x1403:0x0707, size: 5
				this.parent.Menus.F0_2c84_0000_ShowTopMenu(playerID, unitID, -1);
				if (this.parent.Menus
					.ConsumeGoToPathOverlayRefreshRequest())
				{
					RefreshActiveHumanGoToPathMap(
						presentationLease,
						playerID,
						force: true);
				}

				// Instruction address 0x1403:0x070f, size: 5
				this.parent.CommonTools.ClearKeyboardAndMouseEvents();

				if (this.parent.Menus.Var_d4ca_MenuShortcutKey != -1)
				{
					command = this.parent.Menus.Var_d4ca_MenuShortcutKey;

					goto Label151;
				}
				goto Label722;
			}

			if (mouseEvent.Position.X < 80)
			{
				if (mouseEvent.Position.Y < 58)
				{
					//if (mouseEvent.Position.X > 0 && mouseEvent.Position.X < 79 &&
					//	mouseEvent.Position.Y > 8 && mouseEvent.Position.Y < 57)
					//{
					// X: 1-78 (78), Y: 9-56 (48)
					//this.parent.Graphics.F0_VGA_0599_DrawLine(this.parent.Var_aa_Screen0_Rectangle, 1, 9, 78, 9, 6);
					//this.parent.Graphics.F0_VGA_0599_DrawLine(this.parent.Var_aa_Screen0_Rectangle, 1, 56, 78, 56, 6);

					//this.parent.MapManagement.F0_2aea_0008_DrawVisibleMap(playerID, mouseEvent.Position.X - 1, mouseEvent.Position.Y - 9);

					DrawVisibleMapWithPresentation(
						presentationLease,
						playerID,
						unitID,
						this.parent.MapManagement.AdjustXPosition(mouseEvent.Position.X - 7 + this.parent.Var_6ed6_MiniMapX),
						this.parent.Tools.F0_2dc4_007c_CheckValueRange(mouseEvent.Position.Y - 14 + this.parent.Var_70ea_MiniMapY, 0, 49));
					//}
				}
				else if (mouseEvent.Position.Y < 72)
				{
					this.parent.Palace.F17_0000_07ec(0);

					this.parent.Var_aa_Screen0_Rectangle.ScreenID = 0;

					// Instruction address 0x1403:0x07af, size: 5
					this.parent.Tools.F0_2dc4_065f_StopPaletteCycleSlots();

					// Instruction address 0x1403:0x07cc, size: 5
					this.parent.DrawTools.FillRectangle(this.parent.Var_aa_Screen0_Rectangle, 0, 0, 320, 200, 0);

					// Instruction address 0x1403:0x07d8, size: 5
					this.parent.ImageTools.F0_2fa1_01a2_LoadBitmapOrPalette(-1, 0, 0, "CBACK.PIC", 1);

					// Instruction address 0x1403:0x0800, size: 5
					this.parent.Graphics.F0_VGA_07d8_DrawImage(this.parent.Var_19d4_Screen1_Rectangle, 0, 0, 320, 200, this.parent.Var_aa_Screen0_Rectangle, 0, 0);

					// Instruction address 0x1403:0x080d, size: 5
					this.parent.Segment_2459.F0_2459_0918_WaitForKeyPressOrMouseClick();

					// Instruction address 0x1403:0x0826, size: 5
					this.parent.Segment_1238.F0_1238_1b44();

					// Instruction address 0x1403:0x082b, size: 5
					this.parent.Tools.F0_2dc4_0626_StartPaletteCycleSlots();
				}
				else if (unitID >= 128)
				{
					goto Label755;
				}

				//this.parent.Var_db3a_MouseButton = 0;
				mouseEvent = new MouseEvent(mouseEvent.Position, MouseButtonsEnum.None);
			}

			if (mouseEvent.Buttons == MouseButtonsEnum.Right)
			{
				if (unitID < 128)
				{
					while (true)
					{
						mouseEvent = this.parent.GetMouseEvent();

						if (mouseEvent.Buttons == MouseButtonsEnum.None)
						{
							// Instruction address 0x1403:0x0882, size: 5
							mouseX = this.parent.MapManagement.AdjustXPosition((mouseEvent.Position.X - 80) / 16 + this.parent.Var_d4cc_MapViewX);
							mouseY = ((mouseEvent.Position.Y - 8) / 16) + this.parent.Var_d75e_MapViewY;

							// Instruction address 0x1403:0x08d0, size: 5
							int distance = this.parent.Tools.F0_2dc4_0289_GetShortestDistance(
								mouseX - this.parent.GameData.Players[playerID].Units[unitID].Position.X,
								mouseY - this.parent.GameData.Players[playerID].Units[unitID].Position.Y);

							if (Math.Abs(mouseX - this.parent.GameData.Players[playerID].Units[unitID].Position.X) == 79)
							{
								if (Math.Abs(mouseY - this.parent.GameData.Players[playerID].Units[unitID].Position.Y) <= 1)
								{
									distance = 1;
								}
							}

							if (distance == 1)
							{
								// The distance is one cell, we can issue a command for this movement
								Unit unit1 = this.parent.GameData.Players[playerID].Units[unitID];
								GPoint newMove = new GPoint(mouseX - unit1.Position.X, mouseY - unit1.Position.Y);

								command = -1;

								for (int i = 1; i < 9; i++)
								{
									if (this.parent.MoveDirections[i] == newMove)
									{
										command = i;
										break;
									}
								}

								if (command > 0)
								{
									goto Label151;
								}
								//this.parent.GameData.Players[playerID].Units[unitID].GoToDestination = new(mouseX, mouseY);
								//this.parent.GameData.Players[playerID].Units[unitID].GoToNextDirection = -1;

								mouseEvent = new MouseEvent(mouseEvent.Position, MouseButtonsEnum.None);
								//flag3 = false;
							}
							else
							{
								//this.parent.Var_db3a_MouseButton = 2;
								mouseEvent = new MouseEvent(mouseEvent.Position, MouseButtonsEnum.Right);

								if ((this.parent.GameData.MapVisibility[mouseX, mouseY] & (0x1 << this.parent.GameData.HumanPlayerID)) != 0 || this.parent.Var_d806_DebugFlag)
								{
									// Instruction address 0x1403:0x09b4, size: 5
									this.parent.Encyclopedia.F8_0000_062a_DisplayEncyclopediaTopic(EncyclopediaTopicEnum.TerrainType, (int)this.parent.MapManagement.GetTerrainType(mouseX, mouseY));

									// Instruction address 0x1403:0x09c5, size: 5
									this.parent.Segment_1238.F0_1238_1b44();
								}
							}
							break;
						}
					}
				}
			}
			else if (mouseEvent.Buttons == MouseButtonsEnum.Left)
			{
				if (flag3 && unitID < 128)
				{
					ClearHumanGoToHoverPreview(
						presentationLease,
						playerID,
						refresh: false);
					if (selectingRoadToCityTarget)
					{
						int selectedCityID =
							ResolveRoadToCityVisualTarget(
								playerID,
								mouseX,
								mouseY,
								mouseEvent.Position.X,
								mouseEvent.Position.Y);
						selectingRoadToCityTarget = false;
						flag3 = false;
						this.parent.CommonTools.SetMousePositionAndIcon(
							0,
							0,
							this.parent.Array_d4ce[7]);
						if (selectedCityID < 0)
						{
							ShowWorldMapDialogWithPresentation(
								presentationLease,
								playerID,
								unitID,
								ClassicGameText.Current[
									ClassicGameTextKey.RoadToCitySelectOwnCity],
								100,
								80);
						}
						else if (TryPrepareRoadToCityAction(
							presentationLease,
							playerID,
							unitID,
							startRequested: true,
							destinationCityID: selectedCityID,
							out command))
						{
							goto Label151;
						}
					}
					else
					{
						TerrainTypeEnum newTerrainType1 = this.parent.MapManagement.GetTerrainType(mouseX, mouseY);

						// local_36 == 2 || will never happen, because local_36 has only two values 0 and 1
						if ((this.parent.GameData.MapVisibility[mouseX, mouseY] & (0x1 << this.parent.GameData.HumanPlayerID)) != 0 &&
							((this.parent.GameData.Units[(int)this.parent.GameData.Players[playerID].Units[unitID].UnitType].MovementType == UnitMovementTypeEnum.Air && newTerrainType1 == TerrainTypeEnum.Water) ||
							(this.parent.GameData.Units[(int)this.parent.GameData.Players[playerID].Units[unitID].UnitType].MovementType == UnitMovementTypeEnum.Land && newTerrainType1 != TerrainTypeEnum.Water) ||
							(this.parent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(mouseX, mouseY).HasFlag(TerrainImprovementFlagsEnum.City) ||
								this.parent.GameData.Units[(int)this.parent.GameData.Players[playerID].Units[unitID].UnitType].MovementType == UnitMovementTypeEnum.Water)))
						{
							this.parent.GameData.Players[playerID].Units[unitID].GoToDestination = new(mouseX, mouseY);
							this.parent.GameData.Players[playerID].Units[unitID].GoToNextDirection = -1;
						}

						flag3 = false;

						this.parent.CommonTools.SetMousePositionAndIcon(0, 0, this.parent.Array_d4ce[7]);
					}
				}
				else
				{
					if (this.parent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(mouseX, mouseY).HasFlag(TerrainImprovementFlagsEnum.City) &&
						(this.parent.MapManagement.F0_2aea_1369_GetCityOwner(mouseX, mouseY) == this.parent.GameData.HumanPlayerID ||
							this.parent.Var_d806_DebugFlag))
					{
						int cityID = this.parent.Tools.F0_2dc4_00ba_GetCityByLocation(mouseX, mouseY);

						// Instruction address 0x1403:0x0b9a, size: 5
						ShowWorldMapOverlayWithPresentation(
							presentationLease,
							playerID,
							unitID,
							() =>
							{
								this.parent.Segment_1ade.F0_1ade_03ea(cityID);
								this.parent.Segment_1238.F0_1238_107e();
							});

						flag2 = false;
					}
					else
					{
						int activeUnitID1 = this.parent.MapManagement.F0_2aea_1458_GetCellActiveUnitID(mouseX, mouseY);
						int playerID1 = this.parent.MapManagement.F0_2aea_14e0_GetCellActiveUnitPlayerID(mouseX, mouseY);

						if (activeUnitID1 != -1 && this.parent.Var_d806_DebugFlag)
						{
							this.parent.ShowDebugDetails.ShowUnitStatus(playerID1, activeUnitID1);
						}

						if (activeUnitID1 != -1 && playerID == playerID1)
						{
							int local_3a = this.parent.UnitManagement.F0_1866_1f69(playerID1, activeUnitID1);
							TryCancelUnitAutomationForManualControl(
								playerID1,
								local_3a,
								out _);

							if ((this.parent.GameData.Players[playerID].Units[local_3a].Status & (UnitStatusEnum.Sentry | UnitStatusEnum.Fortified)) == UnitStatusEnum.None)
							{
								unitID = local_3a;
								maxUnitID = local_3a;
								if (maxUnitID < 0)
									maxUnitID = 127;

								flag4 = false;
								flag2 = false;
								if (!UsesSmartEnhancements)
								{
									goto Label722;
								}

								spentManualSelectionQolOnly =
									this.parent.GameData.Players[playerID]
										.Units[local_3a].RemainingMoves <= 0;

								// A manually selected unit may have spent its
								// movement already. It still needs one input
								// cycle so a persistent QoL order can be queued
								// for the next turn.
								goto Label79;
							}
						}
						else
						{
							// Instruction address 0x1403:0x0cdd, size: 5
							DrawVisibleMapWithPresentation(
								presentationLease,
								playerID,
								unitID,
								mouseX - 7,
								mouseY - 6);
						}
					}
				}
			}

			// Instruction address 0x1403:0x0cfb, size: 5
			CompleteManualPointerSelection();

		Label151:
			Unit? unit = null;
			TerrainTypeEnum terrainType = TerrainTypeEnum.Invalid;

			if (unitID < 128)
			{
				unit = this.parent.GameData.Players[playerID].Units[unitID];
				terrainType = this.parent.MapManagement.GetTerrainType(unit.Position.X, unit.Position.Y);
			}

			if (unit != null && spentManualSelectionQolOnly)
			{
				if (UsesSmartEnhancements &&
					(command == 'e' || command == 'E' ||
					 command == 'v' || command == 'V' ||
					 command == 'x' || command == 'X'))
				{
					ClearUnitGoTo(unit);
					RefreshActiveHumanGoToPathMap(
						presentationLease,
						playerID);
				}
				else
				{
					command = 0;
				}
			}

			if (unit != null &&
				!spentManualSelectionQolOnly &&
				!preserveSmartAiTransportGoToWait)
			{
				if (unit.GoToDestination.X != -1)
				{
					int command1 = this.parent.UnitGoTo.GetNextGoToMove(playerID, unitID);

					if (command1 == -1)
					{
						unit.GoToDestination = OpenCivOneGame.InvalidPosition;
						unit.GoToNextDirection = -1;
						this.parent.UnitAutomationState.Cancel(
							playerID,
							unitID);
					}
					else
					{
						command = command1;
					}

					RefreshActiveHumanGoToPathMap(
						presentationLease,
						playerID);
				}
				else
				{
					unit.GoToNextDirection = -1;
				}
			}

			int nearestCityID;
			int distanceToObject;
			int newMoveDirection = 0;

			switch (command)
			{
				// Change government
				case -2:
					if (ShowWorldMapDialogWithPresentation(
						presentationLease,
						playerID,
						unitID,
						this.parent.LanguageTools.F0_2f4d_044f_GetTextFromKingSection("*REV"),
						64,
						80) == 1)
					{
						this.parent.GameData.Players[playerID].GovernmentType = 0;

						ShowWorldMapOverlayWithPresentation(
							presentationLease,
							playerID,
							unitID,
							() => this.parent.News.F21_0000_0000_ShowNews(
								-1,
								$"The {this.parent.GameData.Players[playerID].Nation} are\nrevolting! Citizens\ndemand new government.\n"));

						this.parent.StartGameMenu.F5_0000_1af6_LoadGovernmentImage();

						// Instruction address 0x1403:0x35be, size: 5
						this.parent.Segment_1238.F0_1238_1b44();
					}
					break;

				// No command
				case '\0':
					break;

				// Enter or Space
				case '\x0d':
					if (unitID >= 128) goto Label755;
					break;

				// No orders or end of turn
				case ' ':
					if (unitID >= 128) goto Label755;

					if (unit != null)
					{
						unit.RemainingMoves = 0;
					}
					break;

				// Disband
				case 'D':
					if (unit == null || unitID >= 128) break;

					unit.RemainingMoves = 0;

					// Instruction address 0x1403:0x0d90, size: 5
					this.parent.UnitManagement.F0_1866_0f10_DeleteUnit(playerID, unitID);
					break;

				// Pillage
				case 'P':
					if (unit == null || unitID >= 128) break;

					if (!this.parent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(unit.Position.X, unit.Position.Y).HasFlag(TerrainImprovementFlagsEnum.City) &&
						unit.UnitType != UnitTypeEnum.Fighter)
					{
						// Instruction address 0x1403:0x0df1, size: 5
						int cityID = this.parent.Tools.F0_2dc4_0102_FindNearestCity(unit.Position.X, unit.Position.Y);

						if (unit.RemainingMoves != 0)
						{
							if ((short)this.parent.Segment_29f3.F0_29f3_0c9e_ConfirmAttackAction(this.parent.GameData.Cities[cityID].PlayerID) != -1)
							{
								TerrainImprovementFlagsEnum improvements = this.parent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(unit.Position.X, unit.Position.Y);

								if (improvements.HasFlag(TerrainImprovementFlagsEnum.Mines) || improvements.HasFlag(TerrainImprovementFlagsEnum.Irrigation))
								{
									this.parent.MapManagement.F0_2aea_16ee_ClearTerrainImprovements(unit.Position.X, unit.Position.Y, TerrainImprovementFlagsEnum.Mines | TerrainImprovementFlagsEnum.Irrigation);
								}
								else if (improvements.HasFlag(TerrainImprovementFlagsEnum.RailRoad))
								{
									this.parent.MapManagement.F0_2aea_16ee_ClearTerrainImprovements(unit.Position.X, unit.Position.Y, TerrainImprovementFlagsEnum.RailRoad | TerrainImprovementFlagsEnum.Irrigation | TerrainImprovementFlagsEnum.Mines);
								}
								else
								{
									this.parent.MapManagement.F0_2aea_16ee_ClearTerrainImprovements(unit.Position.X, unit.Position.Y, TerrainImprovementFlagsEnum.Road);
								}

								if (this.parent.GameData.Cities[cityID].PlayerID == this.parent.GameData.HumanPlayerID)
								{
									this.parent.MapManagement.F0_2aea_1601_UpdateVisibleCellStatus(unit.Position.X, unit.Position.Y);
								}

								F0_1403_3ed7(unit.Position.X, unit.Position.Y);
								this.parent.Segment_2517.F0_2517_0aa1_ClearDiplomacyFlags(this.parent.GameData.HumanPlayerID,
									this.parent.GameData.Cities[cityID].PlayerID, DiplomacyFlagsEnum.Peace);

								int local_54 = this.parent.GameData.Cities[cityID].PlayerID;

								if (playerID != local_54)
								{
									this.parent.AIEngine.PlayerAddUnitPolicy(local_54, unit.Position.X, unit.Position.Y, UnitRoleTypeEnum.LandAttack, 4);
								}

								unit.RemainingMoves = 0;
							}
						}
					}
					else
					{
						// Instruction address 0x1403:0x0ddd, size: 5
						ShowWorldMapOverlayWithPresentation(
							presentationLease,
							playerID,
							unitID,
							() => this.parent.Help.F4_0000_03aa_ShowInstantWarningPopup("*PILLAGE"));
					}
					break;

				// Build a city
				case 'b':
					if (unit == null || unitID >= 128) break;

					if (unit.UnitType != UnitTypeEnum.Settler)
					{
						// Instruction address 0x1403:0x19dd, size: 5
						ShowWorldMapOverlayWithPresentation(
							presentationLease,
							playerID,
							unitID,
							() => this.parent.Help.F4_0000_03aa_ShowInstantWarningPopup("*SETTLERS"));
					}
					else if (terrainType != TerrainTypeEnum.Water && unit.Position.Y >= 2 && unit.Position.Y < 48)
					{
						if (this.parent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(unit.Position.X, unit.Position.Y).HasFlag(TerrainImprovementFlagsEnum.City))
						{
							int cityID = this.parent.MapManagement.F0_2aea_175a_FindCityHumanPlayer(unit.Position.X, unit.Position.Y);

							if (this.parent.GameData.Cities[cityID].ActualSize < 10)
							{
								GPoint unitPosition = unit.Position;

								this.parent.GameData.Cities[cityID].ActualSize++;

								// Instruction address 0x1403:0x1a6a, size: 5
								this.parent.UnitManagement.F0_1866_0f10_DeleteUnit(playerID, unitID);

								DrawCellWithUnitWithPresentation(
									presentationLease,
									playerID,
									unit.ID,
									unitPosition.X,
									unitPosition.Y);

								// Instruction address 0x1403:0x1a78, size: 5
								//F0_1403_3f13_RedrawUnit(playerID, unitID);
							}
							else
							{
								// Instruction address 0x1403:0x1a87, size: 5
								ShowWorldMapOverlayWithPresentation(
									presentationLease,
									playerID,
									unitID,
									() => this.parent.Help.F4_0000_03aa_ShowInstantWarningPopup("*ADDCITY"));
							}
						}
						else
						{
							unit.RemainingMoves = 0;

							int local_3a = (short)this.parent.Overlay_20.F20_0000_0000(playerID, unit.Position.X, unit.Position.Y, 1);

							if (local_3a != -1)
							{
								// Instruction address 0x1403:0x1ad1, size: 5
								this.parent.UnitManagement.F0_1866_0f10_DeleteUnit(playerID, unitID);

								// Instruction address 0x1403:0x1adf, size: 5
								F0_1403_3f13_RedrawUnit(playerID, unitID);
							}
						}
					}
					break;

				// Fortify unit or build fortress
				case 'f':
					if (unit == null || unitID >= 128) break;

					if (this.parent.GameData.Units[(int)unit.UnitType].MovementType == UnitMovementTypeEnum.Land)
					{
						if (unit.UnitType != UnitTypeEnum.Settler)
						{
							unit.Status |= UnitStatusEnum.Fortifying;
							unit.RemainingMoves = 0;

							// Instruction address 0x1403:0x12bf, size: 5
							F0_1403_3f13_RedrawUnit(playerID, unitID);

							if (playerID != this.parent.GameData.HumanPlayerID &&
								this.parent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(unit.Position.X, unit.Position.Y).HasFlag(TerrainImprovementFlagsEnum.City))
							{
								unit.HomeCityID = (short)this.parent.Tools.F0_2dc4_00ba_GetCityByLocation(unit.Position.X, unit.Position.Y);
							}
						}
						else
						{
							if (this.parent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(unit.Position.X, unit.Position.Y).HasFlag(TerrainImprovementFlagsEnum.City) ||
								this.parent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(unit.Position.X, unit.Position.Y).HasFlag(TerrainImprovementFlagsEnum.Fortress) ||
								!this.parent.Segment_1ade.F0_1ade_22b5_PlayerHasTechnology(playerID, TechnologyAdvanceEnum.Construction))
							{
								unit.ClearStatusFlags(UnitStatusEnum.SettlerBuildFortress);
								unit.SpecialMoves = 0;

								CenterMapWithPresentation(
									presentationLease, playerID, unitID,
									unit.Position.X, unit.Position.Y);
							}
							else
							{
								unit.Status |= UnitStatusEnum.SettlerBuildFortress;
								unit.RemainingMoves = 0;

								// Instruction address 0x1403:0x1388, size: 5
								F0_1403_3f13_RedrawUnit(playerID, unitID);

								unit.SpecialMoves++;

								if ((this.parent.GameData.Terrains[(int)terrainType].MovementCost + 4) <= unit.SpecialMoves)
								{
									// Instruction address 0x1403:0x13bf, size: 5
									this.parent.MapManagement.F0_2aea_1653_SetTerrainImprovements(unit.Position.X, unit.Position.Y, TerrainImprovementFlagsEnum.Fortress);

									// Instruction address 0x1403:0x13db, size: 5
									this.parent.UnitManagement.F0_1866_01dc(unit.Position.X, unit.Position.Y, playerID, unitID, true);

									unit.ClearStatusFlags(UnitStatusEnum.SettlerBuildFortress);
									unit.SpecialMoves = 0;
								}
							}
						}
					}
					break;

				// Go To
				case 'g':
					if (unit == null || unitID >= 128) break;

					selectingRoadToCityTarget = false;
					int local_56 = 0;

					if (flag3)
					{
						local_56 = 7;
					}
					else
					{
						local_56 = 2;
					}

					this.parent.CommonTools.SetMousePositionAndIcon(0, 0, this.parent.Array_d4ce[local_56]);

					flag3 ^= true;
					if (!flag3)
					{
						ClearHumanGoToHoverPreview(
							presentationLease,
							playerID,
							refresh: true);
					}
					break;

				// Set as new home city
				case 'h':
					if (unit == null || unitID >= 128) break;

					nearestCityID = this.parent.Tools.F0_2dc4_0102_FindNearestCity(unit.Position.X, unit.Position.Y);

					if (nearestCityID != -1 &&
						(distanceToObject = this.parent.Tools.F0_2dc4_0289_GetShortestDistance(unit.Position.X, unit.Position.Y, this.parent.GameData.Cities[nearestCityID].Position)) == 0)
					{
						unit.HomeCityID = (short)nearestCityID;
					}
					else if (this.parent.GameData.Units[(int)unit.UnitType].MovementType == UnitMovementTypeEnum.Water)
					{
						// Instruction address 0x1403:0x1118, size: 5
						int nearestCityDirection = this.parent.UnitManagement.F0_1866_226d_GetNearestCityDirection(playerID, unitID);

						if (nearestCityDirection != 0)
						{
							unit.Status |= UnitStatusEnum.SettlerBuildRoadOrRail;
							MoveUnitWithPresentation(
								presentationLease,
								playerID,
								unit,
								newMoveDirection,
								ref unitMoveCount);
							break;
						}
						else
						{
							if (playerID == this.parent.GameData.HumanPlayerID)
							{
								unit.ClearStatusFlags(UnitStatusEnum.SettlerBuildRoadOrRail);
							}
							else
							{
								// Instruction address 0x1403:0x1175, size: 5
								this.parent.UnitManagement.F0_1866_0f10_DeleteUnit(playerID, unitID);
							}
						}
					}
					break;

				// Build irrigation
				case 'i':
					if (unit == null || unitID >= 128) break;

					if (unit.UnitType != UnitTypeEnum.Settler ||
						(this.parent.GameData.DebugFlags & 0x2) == 0 ||
						this.parent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(unit.Position.X, unit.Position.Y).HasFlag(TerrainImprovementFlagsEnum.Irrigation))
					{
						// Instruction address 0x1403:0x15ce, size: 5
						CenterMapWithPresentation(
							presentationLease, playerID, unitID,
							unit.Position.X, unit.Position.Y);

						if (unit.UnitType != UnitTypeEnum.Settler)
						{
							ShowWorldMapOverlayWithPresentation(
								presentationLease,
								playerID,
								unitID,
								() => this.parent.Help.F4_0000_03aa_ShowInstantWarningPopup("*SETTLERS"));
						}
						else
						{
							unit.SpecialMoves = 0;
						}

						unit.ClearStatusFlags(UnitStatusEnum.SettlerBuildIrrigation);
					}
					else
					{
						int irrigatedTerrainType = this.parent.GameData.TerrainModifications[(int)terrainType].IrrigationEffect;

						if (irrigatedTerrainType == -1)
						{
							// Instruction address 0x1403:0x165e, size: 5
							CenterMapWithPresentation(
								presentationLease, playerID, unitID,
								unit.Position.X, unit.Position.Y);
							ShowWorldMapOverlayWithPresentation(
								presentationLease,
								playerID,
								unitID,
								() => this.parent.Help.F4_0000_03aa_ShowInstantWarningPopup("*NOIRR"));

							unit.ClearStatusFlags(UnitStatusEnum.SettlerBuildIrrigation);
						}
						else
						{
							if (irrigatedTerrainType != -2 || this.parent.MapManagement.CanIrrigateCell(unit.Position.X, unit.Position.Y))
							{
								unit.Status |= UnitStatusEnum.SettlerBuildIrrigation;

								// Instruction address 0x1403:0x16f9, size: 5
								F0_1403_3f13_RedrawUnit(playerID, unitID);

								unit.RemainingMoves = 0;
								unit.GoToDestination = OpenCivOneGame.InvalidPosition;
								unit.GoToNextDirection = -1;
								unit.SpecialMoves++;

								if (this.parent.GameData.TerrainModifications[(int)terrainType].IrrigationCost <= unit.SpecialMoves)
								{
									if (irrigatedTerrainType >= 0)
									{
										// Instruction address 0x1403:0x1743, size: 5
										this.parent.MapManagement.SetTerrainType(unit.Position.X, unit.Position.Y, this.parent.PixelValuesToTerrainTypes[irrigatedTerrainType]);

										this.parent.GameData.MapVisibility[unit.Position.X, unit.Position.Y] |= 1;

										// Instruction address 0x1403:0x176a, size: 5
										this.parent.MapManagement.F0_2aea_16ee_ClearTerrainImprovements(unit.Position.X, unit.Position.Y, TerrainImprovementFlagsEnum.Irrigation | TerrainImprovementFlagsEnum.Mines);
									}
									else
									{
										// Instruction address 0x1403:0x177f, size: 5
										this.parent.MapManagement.F0_2aea_16ee_ClearTerrainImprovements(unit.Position.X, unit.Position.Y, TerrainImprovementFlagsEnum.Mines);
										// Instruction address 0x1403:0x1791, size: 5
										this.parent.MapManagement.F0_2aea_1653_SetTerrainImprovements(unit.Position.X, unit.Position.Y, TerrainImprovementFlagsEnum.Irrigation);
									}

									// Instruction address 0x1403:0x179f, size: 5
									F0_1403_3f13_RedrawUnit(playerID, unitID);

									unit.ClearStatusFlags(UnitStatusEnum.SettlerBuildIrrigation);
									unit.SpecialMoves = 0;
								}
							}
							else
							{
								// Instruction address 0x1403:0x16b2, size: 5
								CenterMapWithPresentation(
									presentationLease, playerID, unitID,
									unit.Position.X, unit.Position.Y);
								// Instruction address 0x1403:0x16be, size: 5
								ShowWorldMapOverlayWithPresentation(
									presentationLease,
									playerID,
									unitID,
									() => this.parent.Help.F4_0000_03aa_ShowInstantWarningPopup("*NOWATER"));

								unit.ClearStatusFlags(UnitStatusEnum.SettlerBuildIrrigation);
							}
						}
					}
					break;

				// Build forest or mine
				case 'm':
					if (unit == null || unitID >= 128) break;

					if (unit.UnitType != UnitTypeEnum.Settler ||
						this.parent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(unit.Position.X, unit.Position.Y).HasFlag(TerrainImprovementFlagsEnum.Mines))
					{
						// Instruction address 0x1403:0x17fc, size: 5
						CenterMapWithPresentation(
							presentationLease, playerID, unitID,
							unit.Position.X, unit.Position.Y);

						if (unit.UnitType != UnitTypeEnum.Settler)
						{
							// Instruction address 0x1403:0x1822, size: 5
							ShowWorldMapOverlayWithPresentation(
								presentationLease,
								playerID,
								unitID,
								() => this.parent.Help.F4_0000_03aa_ShowInstantWarningPopup("*SETTLERS"));
						}
						else
						{
							unit.SpecialMoves = 0;
						}

						unit.ClearStatusFlags(UnitStatusEnum.SettlerBuildMineOrForest);
					}
					else
					{
						int minedTerrainType = this.parent.GameData.TerrainModifications[(int)terrainType].MiningEffect;

						if (minedTerrainType == -1)
						{
							// Instruction address 0x1403:0x188c, size: 5
							CenterMapWithPresentation(
								presentationLease, playerID, unitID,
								unit.Position.X, unit.Position.Y);
							// Instruction address 0x1403:0x1898, size: 5
							ShowWorldMapOverlayWithPresentation(
								presentationLease,
								playerID,
								unitID,
								() => this.parent.Help.F4_0000_03aa_ShowInstantWarningPopup("*NOMINE"));

							unit.ClearStatusFlags(UnitStatusEnum.SettlerBuildMineOrForest);
						}
						else
						{
							unit.Status |= UnitStatusEnum.SettlerBuildMineOrForest;

							// Instruction address 0x1403:0x18d3, size: 5
							F0_1403_3f13_RedrawUnit(playerID, unitID);

							unit.RemainingMoves = 0;
							unit.GoToDestination = OpenCivOneGame.InvalidPosition;
							unit.GoToNextDirection = -1;
							unit.SpecialMoves++;

							if (this.parent.GameData.TerrainModifications[(int)terrainType].MiningCost <= unit.SpecialMoves)
							{
								if (minedTerrainType >= 0)
								{
									unit.SpecialMoves++;

									if (unit.SpecialMoves > 5)
									{
										// Instruction address 0x1403:0x193e, size: 5
										this.parent.MapManagement.SetTerrainType(unit.Position.X, unit.Position.Y, this.parent.PixelValuesToTerrainTypes[minedTerrainType]);

										this.parent.GameData.MapVisibility[unit.Position.X, unit.Position.Y] |= 1;

										// Instruction address 0x1403:0x1965, size: 5
										this.parent.MapManagement.F0_2aea_16ee_ClearTerrainImprovements(unit.Position.X, unit.Position.Y, TerrainImprovementFlagsEnum.Mines | TerrainImprovementFlagsEnum.Irrigation);
										// Instruction address 0x1403:0x199a, size: 5
										F0_1403_3f13_RedrawUnit(playerID, unitID);

										unit.ClearStatusFlags(UnitStatusEnum.SettlerBuildMineOrForest);
										unit.SpecialMoves = 0;
									}
								}
								else
								{
									// Instruction address 0x1403:0x197a, size: 5
									this.parent.MapManagement.F0_2aea_16ee_ClearTerrainImprovements(unit.Position.X, unit.Position.Y, TerrainImprovementFlagsEnum.Irrigation);
									// Instruction address 0x1403:0x198c, size: 5
									this.parent.MapManagement.F0_2aea_1653_SetTerrainImprovements(unit.Position.X, unit.Position.Y, TerrainImprovementFlagsEnum.Mines);
									// Instruction address 0x1403:0x199a, size: 5
									F0_1403_3f13_RedrawUnit(playerID, unitID);

									unit.ClearStatusFlags(UnitStatusEnum.SettlerBuildMineOrForest);
									unit.SpecialMoves = 0;
								}
							}
						}
					}
					break;

				// Clear pollution
				case 'p':
					if (unit == null || unitID >= 128) break;

					if (unit.UnitType != UnitTypeEnum.Settler)
					{
						// Instruction address 0x1403:0x119e, size: 5
						ShowWorldMapOverlayWithPresentation(
							presentationLease, playerID, unitID,
							() => this.parent.Help.F4_0000_03aa_ShowInstantWarningPopup("*SETTLERS"));
					}
					else
					{
						TerrainImprovementFlagsEnum terrainImprovements = this.parent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(unit.Position.X, unit.Position.Y);

						if (!terrainImprovements.HasFlag(TerrainImprovementFlagsEnum.Pollution))
						{
							unit.ClearStatusFlags(UnitStatusEnum.SettlerCleanPollution);
							unit.SpecialMoves = 0;

							// Instruction address 0x1403:0x11e6, size: 5
							CenterMapWithPresentation(
								presentationLease, playerID, unitID,
								unit.Position.X, unit.Position.Y);
						}
						else
						{
							unit.Status |= UnitStatusEnum.SettlerCleanPollution;

							// Instruction address 0x1403:0x120c, size: 5
							F0_1403_3f13_RedrawUnit(playerID, unitID);

							unit.RemainingMoves = 0;
							unit.GoToDestination = OpenCivOneGame.InvalidPosition;
							unit.GoToNextDirection = -1;
							unit.SpecialMoves++;

							if (unit.SpecialMoves >= 4)
							{
								// Instruction address 0x1403:0x123e, size: 5
								this.parent.MapManagement.F0_2aea_16ee_ClearTerrainImprovements(unit.Position.X, unit.Position.Y, TerrainImprovementFlagsEnum.Pollution);
								// Instruction address 0x1403:0x124c, size: 5
								this.parent.MapManagement.F0_2aea_1601_UpdateVisibleCellStatus(unit.Position.X, unit.Position.Y);

								this.parent.GameData.PollutedSquareCount--;

								// Instruction address 0x1403:0x125e, size: 5
								F0_1403_3f13_RedrawUnit(playerID, unitID);

								unit.ClearStatusFlags(UnitStatusEnum.SettlerCleanPollution);
								unit.SpecialMoves = 0;
							}
						}
					}
					break;

				// Build roads or railroads
				case 'r':
					if (unit == null || unitID >= 128) break;

					if (unit.UnitType != UnitTypeEnum.Settler)
					{
						// Instruction address 0x1403:0x141e, size: 5
						ShowWorldMapOverlayWithPresentation(
							presentationLease, playerID, unitID,
							() => this.parent.Help.F4_0000_03aa_ShowInstantWarningPopup("*SETTLERS"));
					}
					else
					{
						TerrainImprovementFlagsEnum terrainImprovements = this.parent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(unit.Position.X, unit.Position.Y);

						if (terrainType == TerrainTypeEnum.Water ||
							(terrainImprovements.HasFlag(TerrainImprovementFlagsEnum.Road) &&
							(!this.parent.Segment_1ade.F0_1ade_22b5_PlayerHasTechnology(playerID, TechnologyAdvanceEnum.Railroad) ||
							terrainImprovements.HasFlag(TerrainImprovementFlagsEnum.City))) || terrainImprovements.HasFlag(TerrainImprovementFlagsEnum.RailRoad))
						{
							unit.ClearStatusFlags(UnitStatusEnum.SettlerBuildRoadOrRail);
							unit.SpecialMoves = 0;

							// Instruction address 0x1403:0x148f, size: 5
							CenterMapWithPresentation(
								presentationLease, playerID, unitID,
								unit.Position.X, unit.Position.Y);
						}
						else
						{
							if (terrainType != TerrainTypeEnum.River || this.parent.Segment_1ade.F0_1ade_22b5_PlayerHasTechnology(playerID, TechnologyAdvanceEnum.BridgeBuilding))
							{
								unit.Status |= UnitStatusEnum.SettlerBuildRoadOrRail;
								unit.RemainingMoves = 0;

								// Instruction address 0x1403:0x14ee, size: 5
								F0_1403_3f13_RedrawUnit(playerID, unitID);

								int local_58 = unit.SpecialMoves;

								unit.SpecialMoves++;

								if ((((terrainImprovements.HasFlag(TerrainImprovementFlagsEnum.Road)) ? 4 : 2) * this.parent.GameData.Terrains[(int)terrainType].MovementCost) <= local_58)
								{
									// Instruction address 0x1403:0x154b, size: 5
									this.parent.MapManagement.F0_2aea_1653_SetTerrainImprovements(
										unit.Position.X, unit.Position.Y, ((terrainImprovements.HasFlag(TerrainImprovementFlagsEnum.Road)) ? TerrainImprovementFlagsEnum.RailRoad : TerrainImprovementFlagsEnum.Road));
									// Instruction address 0x1403:0x1567, size: 5
									this.parent.UnitManagement.F0_1866_01dc(unit.Position.X, unit.Position.Y, playerID, unitID, true);

									unit.ClearStatusFlags(UnitStatusEnum.SettlerBuildRoadOrRail);
									unit.SpecialMoves = 0;
								}
							}
						}
					}
					break;

				// Sentry unit
				case 's':
					if (unit == null || unitID >= 128) break;

					unit.Status |= UnitStatusEnum.Sentry;
					unit.RemainingMoves = 0;

					// Instruction address 0x1403:0x0f64, size: 5
					F0_1403_3f13_RedrawUnit(playerID, unitID);

					break;

				// Unload unit from carrier
				case 'u':
					if (unit == null || unitID >= 128) break;

					if (this.parent.GameData.Units[(int)unit.UnitType].TransportCapacity != 0 || unit.UnitType == UnitTypeEnum.Carrier)
					{
						if (unit.NextUnitID != -1)
						{
							// Instruction address 0x1403:0x0fc8, size: 5
							this.parent.UnitManagement.F0_1866_14f6_UnitStack(playerID, unitID);

							flag2 = false;
							flag7 = true;
							unitID = F0_1403_4562(playerID, unitID) - 1;
							maxUnitID = unitID;
							if (maxUnitID < 0)
								maxUnitID = 127;

							flag4 = false;
						}
					}
					break;

				// Automatic explore
				case 'E':
				case 'e':
					if (unit == null || unitID >= 128)
					{
						break;
					}

					if (!UsesSmartEnhancements)
					{
						break;
					}

					if (TryHandleAutomaticExploreShortcut(
						playerID,
						unitID,
						automaticExploreInterruptedByManualInput,
						out int exploreCommand,
						out automaticExploreObservation))
					{
						command = exploreCommand;
						automaticExploreMove = true;
						goto Label151;
					}
					break;

				// Select an owned destination city and build a road to it
				case 'X':
				case 'x':
					if (unit == null ||
						unitID >= 128 ||
						!UsesSmartEnhancements ||
						unit.UnitType != UnitTypeEnum.Settler)
					{
						break;
					}

					selectingRoadToCityTarget = true;
					this.parent.CommonTools.SetMousePositionAndIcon(
						0,
						0,
						this.parent.Array_d4ce[2]);
					flag3 = true;
					break;

				// Improve the nearest city with a known modernization need
				case 'V':
				case 'v':
					if (unit == null || unitID >= 128)
					{
						break;
					}

					if (!UsesSmartEnhancements)
					{
						break;
					}

					if (TryPrepareImproveNearestCityAction(
						presentationLease,
						playerID,
						unitID,
						startRequested: true,
						out int improveCommand))
					{
						command = improveCommand;
						goto Label151;
					}
					break;

				// wait for orders
				case 'w':
					if (unit == null || unitID >= 128) break;

					flag7 = true;
					flag4 = true;

					break;

				// Wake every sentried or fortified unit of this type
				case 'W':
					if (unit == null ||
						unitID >= 128 ||
						!UsesSmartEnhancements)
					{
						break;
					}

					int wokenUnitCount =
						ClassicWakeUnitTypeRuntime.TryWakeAll(
							this.parent.GameData,
							playerID,
							unit.UnitType);
					this.parent.Host.ShowTransientStatus(
						ClassicGameText.Current.Format(
							ClassicGameTextKey
								.WakeAllOfTypeResult,
							wokenUnitCount,
							ClassicDisplayNames.Unit(
								unit.UnitType,
								this.parent.GameData.Units[
									(int)unit.UnitType].Name)));
					break;

				// Show a read-only, knowledge-safe Caravan trade suggestion
				case 'T':
					if (unit == null ||
						unitID >= 128 ||
						!UsesSmartEnhancements ||
						!this.parent.GameData.GameSettingFlags
							.CaravanTradeAdvisor ||
						unit.UnitType != UnitTypeEnum.Caravan)
					{
						break;
					}

					ShowCaravanTradeAdvisor(playerID, unitID);
					break;

				// Center map on unit
				case 'c':
					if (unit == null || unitID >= 128) break;

					DrawVisibleMapWithPresentation(
						presentationLease,
						playerID,
						unitID,
						unit.Position.X - 7,
						unit.Position.Y - 6);
					break;

				// Move unit Up
				case '\x001':
				case '\x4800':
					ExecuteMoveUnitWithPresentation(
						presentationLease,
						playerID,
						unit,
						1,
						ref unitMoveCount,
						automaticExploreMove,
						automaticExploreObservation);
					break;

				// Move unit PageUp
				case '\x002':
				case '\x4900':
					ExecuteMoveUnitWithPresentation(
						presentationLease,
						playerID,
						unit,
						2,
						ref unitMoveCount,
						automaticExploreMove,
						automaticExploreObservation);
					break;

				// Move unit Right
				case '\x003':
				case '\x4d00':
					ExecuteMoveUnitWithPresentation(
						presentationLease,
						playerID,
						unit,
						3,
						ref unitMoveCount,
						automaticExploreMove,
						automaticExploreObservation);
					break;

				// Move unit PageDown
				case '\x004':
				case '\x5100':
					ExecuteMoveUnitWithPresentation(
						presentationLease,
						playerID,
						unit,
						4,
						ref unitMoveCount,
						automaticExploreMove,
						automaticExploreObservation);
					break;

				// Move unit Down
				case '\x005':
				case '\x5000':
					ExecuteMoveUnitWithPresentation(
						presentationLease,
						playerID,
						unit,
						5,
						ref unitMoveCount,
						automaticExploreMove,
						automaticExploreObservation);
					break;

				// Move unit End
				case '\x006':
				case '\x4f00':
					ExecuteMoveUnitWithPresentation(
						presentationLease,
						playerID,
						unit,
						6,
						ref unitMoveCount,
						automaticExploreMove,
						automaticExploreObservation);
					break;

				// Move unit Left
				case '\x007':
				case '\x4b00':
					ExecuteMoveUnitWithPresentation(
						presentationLease,
						playerID,
						unit,
						7,
						ref unitMoveCount,
						automaticExploreMove,
						automaticExploreObservation);
					break;

				// Move unit Home
				case '\x008':
				case '\x4700':
					ExecuteMoveUnitWithPresentation(
						presentationLease,
						playerID,
						unit,
						8,
						ref unitMoveCount,
						automaticExploreMove,
						automaticExploreObservation);
					break;

				// Change tax rate
				case '+':
				case '=':
					StringBuilder taxOptions = new();

					taxOptions.Append(
						BuildRateMenuPrefix(
							"Select new Tax rate:",
							this.UsesSmartEnhancements
								? Get1991PlusEconomyForecastLine(
									playerID)
								: null));

					if (!ClassicEconomyRatePolicy.TryReadStoredRates(
						this.parent.GameData.Players[playerID].TaxRate,
						this.parent.GameData.Players[playerID].ScienceTaxRate,
						out ClassicEconomyAllocation currentTaxAllocation))
					{
						break;
					}

					for (int i = 0;
						currentTaxAllocation.TaxRate + currentTaxAllocation.ScienceRate >= i;
						i++)
					{
						if (!ClassicEconomyRatePolicy.TrySelectTaxRate(
							currentTaxAllocation.TaxRate,
							currentTaxAllocation.ScienceRate,
							i,
							out ClassicEconomyAllocation optionAllocation))
						{
							continue;
						}

						// Instruction address 0x1403:0x362a, size: 5
						taxOptions.Append($"{optionAllocation.TaxRate * 10}% Tax, " +
							$"({optionAllocation.ScienceRate * 10}% Science)\n ");
					}

					this.parent.Var_2f9a_MenuBoxDefaultOptionIndex = this.parent.GameData.Players[playerID].TaxRate;

					// Instruction address 0x1403:0x368b, size: 5
					int selectedTaxRate = ShowWorldMapDialogWithPresentation(
						presentationLease,
						playerID,
						unitID,
						taxOptions.ToString(),
						100,
						80);

					if (ClassicEconomyRatePolicy.TrySelectTaxRate(
						currentTaxAllocation.TaxRate,
						currentTaxAllocation.ScienceRate,
						selectedTaxRate,
						out ClassicEconomyAllocation selectedTaxAllocation))
					{
						this.parent.GameData.Players[playerID].ScienceTaxRate =
							(short)selectedTaxAllocation.ScienceRate;
						this.parent.GameData.Players[playerID].TaxRate =
							(short)selectedTaxAllocation.TaxRate;

						// Instruction address 0x1403:0x36b1, size: 5
						this.parent.Segment_1238.F0_1238_107e();
					}
					break;

				// Change luxury rate
				case '-':
				case '_':
					StringBuilder luxuryOptions = new();

					// Instruction address 0x1403:0x36c1, size: 5
					luxuryOptions.Append(
						BuildRateMenuPrefix(
							"Select new Luxuries rate:",
							this.UsesSmartEnhancements
								? Get1991PlusEconomyForecastLine(
									playerID)
								: null));

					int currentPlayerTaxRate =
						this.parent.GameData.Players[playerID].TaxRate;
					if (!ClassicEconomyRatePolicy.TrySelectLuxuryRate(
						currentPlayerTaxRate,
						selectedLuxuryRate: 0,
						out _))
					{
						break;
					}

					int currentLuxuryRate = 0;
					if (ClassicEconomyRatePolicy.TryReadStoredRates(
						currentPlayerTaxRate,
						this.parent.GameData.Players[playerID].ScienceTaxRate,
						out ClassicEconomyAllocation currentLuxuryAllocation))
					{
						currentLuxuryRate = currentLuxuryAllocation.LuxuryRate;
					}

					for (int i = 0;
						ClassicEconomyRatePolicy.TotalRate -
							currentPlayerTaxRate >= i;
						i++)
					{
						if (!ClassicEconomyRatePolicy.TrySelectLuxuryRate(
							currentPlayerTaxRate,
							i,
							out ClassicEconomyAllocation optionAllocation))
						{
							continue;
						}

						luxuryOptions.Append($"{optionAllocation.LuxuryRate * 10}% Luxuries, " +
							$"({optionAllocation.ScienceRate * 10}% Science)\n ");
					}

					this.parent.Var_2f9a_MenuBoxDefaultOptionIndex = currentLuxuryRate;

					int newLuxuryRate = ShowWorldMapDialogWithPresentation(
						presentationLease,
						playerID,
						unitID,
						luxuryOptions.ToString(),
						100,
						80);

					if (ClassicEconomyRatePolicy.TrySelectLuxuryRate(
						currentPlayerTaxRate,
						newLuxuryRate,
						out ClassicEconomyAllocation selectedLuxuryAllocation))
					{
						this.parent.GameData.Players[playerID].ScienceTaxRate =
							(short)selectedLuxuryAllocation.ScienceRate;
						// Instruction address 0x1403:0x37a3, size: 5
						this.parent.Segment_1238.F0_1238_107e();
					}
					break;

				// Find city
				case '/':
				case '?':
					this.parent.TextBoxDialogs.F23_0000_025b_FindCityDialog();
					break;

				// Save game
				case 'S':
					// Enable Save game with zero turns
					//if (this.oParent.GameData.TurnCount != 0)
					//{
					// All Top menus are saving the current screenshot, so should we in Save game shortcut
					this.parent.Graphics.F0_VGA_07d8_DrawImage(this.parent.Var_aa_Screen0_Rectangle, 0, 0, 320, 200, this.parent.Var_19d4_Screen1_Rectangle, 0, 0);

					this.parent.LoadAndSave.F11_0000_036a_SaveGameDialog(false);
					//}
					break;

				// Load game (1991+ shell only)
				case 'L':
					if (TryLoadGameFromPlayerTurn())
					{
						return;
					}
					break;

				// Temporarily remove units from a map
				case 't':
					// In 1991+, the visible Caravan command uses T as its
					// mnemonic. Accept the unshifted key as well so the
					// direct shortcut and the Orders menu execute the same
					// read-only advisor. Non-Caravans and Original 1991 keep
					// the classic temporary-unit-hide command below.
					if (unit != null &&
						unitID < 128 &&
						UsesSmartEnhancements &&
						this.parent.GameData.GameSettingFlags
							.CaravanTradeAdvisor &&
						unit.UnitType == UnitTypeEnum.Caravan)
					{
						ShowCaravanTradeAdvisor(playerID, unitID);
						break;
					}

					presentationLease.RunInteractiveWorldMapAnimation(
						playerID,
						unitID < 128 ? unitID : -1,
						() =>
						{
							this.parent.Var_dcfc = 1;
							this.parent.MapManagement.F0_2aea_0008_DrawVisibleMap(
								playerID,
								this.parent.Var_d4cc_MapViewX,
								this.parent.Var_d75e_MapViewY);
							this.parent.Segment_2459.F0_2459_0918_WaitForKeyPressOrMouseClick();
							this.parent.Var_dcfc = 0;
							this.parent.MapManagement.F0_2aea_0008_DrawVisibleMap(
								playerID,
								this.parent.Var_d4cc_MapViewX,
								this.parent.Var_d75e_MapViewY);
						});
					break;

				// Alt + Q - Quit game
				case 0x1000:
					if (ShowWorldMapDialogWithPresentation(
						presentationLease,
						playerID,
						unitID,
						"Are you sure you\nwant to Quit?\n Keep Playing\n Yes, Quit\n",
						100,
						80) != 1)
					{
						this.parent.Var_dc48_GameEndType = 0;
					}
					else
					{
						if (this.parent.Var_dc48_GameEndType == 0)
						{
							this.parent.Var_dc48_GameEndType = 1;
						}
						unitID = 128;
					}
					break;

				// Alt + W - Show world menu
				case 0x1100:
					// Instruction address 0x1403:0x3a84, size: 5
					this.parent.Menus.F0_2c84_0000_ShowTopMenu(playerID, unitID, 3);

					if (this.parent.Menus.Var_d4ca_MenuShortcutKey != -1)
					{
						command = this.parent.Menus.Var_d4ca_MenuShortcutKey;
						goto Label151;
					}
					break;

				// Alt + R - Randomize leader personalities
				case 0x1300:
					for (int i = 0; i < 16; i++)
					{
						// Instruction address 0x1403:0x3805, size: 5
						this.parent.GameData.Nations[i].Mood = (short)(this.parent.CAPI.RNG.Next(3) - 1); // -1 = Friendly, 0 = Neutral, 1 = Aggressive

						// Instruction address 0x1403:0x3816, size: 5
						this.parent.GameData.Nations[i].Policy = (short)(this.parent.CAPI.RNG.Next(3) - 1); // -1 = Perfectionist, 0 = Neutral, 1 = Expansionist

						// Instruction address 0x1403:0x3827, size: 5
						this.parent.GameData.Nations[i].Ideology = (short)(this.parent.CAPI.RNG.Next(3) - 1); // -1 = Militaristic, 0 = Neutral, 1 = Civilized
					}

					// Instruction address 0x1403:0x3843, size: 5
					ShowWorldMapOverlayWithPresentation(
						presentationLease,
						playerID,
						unitID,
						() => this.parent.Segment_1238
							.F0_1238_001e_ShowDialog(0x2003, 100, 80));
					break;

				// Alt + O - Show Order menu
				case 0x1800:
					// Instruction address 0x1403:0x3a5a, size: 5
					this.parent.Menus.F0_2c84_0000_ShowTopMenu(playerID, unitID, 1);

					if (this.parent.Menus.Var_d4ca_MenuShortcutKey != -1)
					{
						command = this.parent.Menus.Var_d4ca_MenuShortcutKey;
						goto Label151;
					}
					break;

				// Alt + A - Show Advisors menu
				case 0x1e00:
					// Instruction address 0x1403:0x3a6f, size: 5
					this.parent.Menus.F0_2c84_0000_ShowTopMenu(playerID, unitID, 2);

					if (this.parent.Menus.Var_d4ca_MenuShortcutKey != -1)
					{
						command = this.parent.Menus.Var_d4ca_MenuShortcutKey;
						goto Label151;
					}
					break;

				// Alt + D - Activate / Deactivate debug mode
				case 0x2000:
					this.parent.Var_d806_DebugFlag = !this.parent.Var_d806_DebugFlag;

					// Instruction address 0x1403:0x3506, size: 5
					DrawVisibleMapWithPresentation(
						presentationLease,
						this.parent.GameData.HumanPlayerID,
						unitID,
						this.parent.Var_d4cc_MapViewX,
						this.parent.Var_d75e_MapViewY);
					break;

				// Alt + G - Show Game menu
				case 0x2200:
					// Instruction address 0x1403:0x3a45, size: 5
					this.parent.Menus.F0_2c84_0000_ShowTopMenu(playerID, unitID, 0);
					if (this.parent.Menus
						.ConsumeGoToPathOverlayRefreshRequest())
					{
						RefreshActiveHumanGoToPathMap(
							presentationLease,
							playerID,
							force: true);
					}

					if (this.parent.Menus.Var_d4ca_MenuShortcutKey != -1)
					{
						command = this.parent.Menus.Var_d4ca_MenuShortcutKey;
						goto Label151;
					}
					break;

				// Alt + H - Show additional Help
				case 0x2300:
					ShowWorldMapOverlayWithPresentation(
						presentationLease, playerID, unitID,
						() => this.parent.Help.F4_0000_02d3_ShowInstantAdvicePopup("*HELP1"));
					ShowWorldMapOverlayWithPresentation(
						presentationLease, playerID, unitID,
						() => this.parent.Help.F4_0000_02d3_ShowInstantAdvicePopup("*HELP2"));
					break;

				// Alt + C - Show Encyclopedia menu
				case 0x2e00:
					// Instruction address 0x1403:0x3a99, size: 5
					this.parent.Menus.F0_2c84_0000_ShowTopMenu(playerID, unitID, 4);

					if (this.parent.Menus.Var_d4ca_MenuShortcutKey != -1)
					{
						command = this.parent.Menus.Var_d4ca_MenuShortcutKey;
						goto Label151;
					}
					break;

				// Alt + V - Enable/Disable Sound
				case 0x2f00:
					this.parent.CommonTools.SetSoundEnabled(
						!this.parent.GameData.GameSettingFlags.Sound);

					// Instruction address 0x1403:0x3890, size: 5
					ShowWorldMapDialogWithPresentation(
						presentationLease,
						playerID,
						unitID,
						$"Sounds {((this.parent.GameData.GameSettingFlags.Sound) ? "ON\n" : "OFF\n")}",
						100,
						80);
					break;

				// F1 - City status
				case 0x3b00:
					if (this.parent.Var_d806_DebugFlag)
					{
						this.parent.ShowDebugDetails.ShowMapWithStrategy();
					}
					else
					{
						this.parent.Overlay_14.F14_0000_186f_CityStatus(this.parent.GameData.HumanPlayerID);
					}
					break;

				// F2 - Military Advisor
				case 0x3c00:
					if (this.parent.Var_d806_DebugFlag)
					{
						this.parent.ShowDebugDetails.ShowUnitStatistics();
					}
					else
					{
						this.parent.Overlay_14.F14_0000_03ad_MilitaryReport(this.parent.GameData.HumanPlayerID);
					}
					break;

				// F3 - Intelligence Advisor
				case 0x3d00:
					if (this.parent.Var_d806_DebugFlag)
					{
						// Instruction address 0x1403:0x33ae, size: 5
						this.parent.CommonTools.F0_1000_0846(2);

						// Instruction address 0x1403:0x33b6, size: 5
						this.parent.CAPI.getch();

						// Instruction address 0x1403:0x33bf, size: 5
						this.parent.CommonTools.F0_1000_0846(0);
					}
					else
					{
						this.parent.Overlay_14.F14_0000_0d43_IntelligenceReport();
					}
					break;

				// F4 - Attitude Advisor
				case 0x3e00:
					this.parent.Overlay_14.F14_0000_15f4_AttitudeReport(this.parent.GameData.HumanPlayerID);
					break;

				// F5 - Trade Advisor
				case 0x3f00:
					this.parent.Overlay_14.F14_0000_07f1_TradeReport(this.parent.GameData.HumanPlayerID);
					break;

				// F6 - Science Advisor
				case 0x4000:
					this.parent.Overlay_14.F14_0000_014b_ScienceReport(this.parent.GameData.HumanPlayerID);
					break;

				// F7 - Wonders of the World
				case 0x4100:
					if (this.parent.Var_d806_DebugFlag)
					{
						for (int i = 1; i < 8; i++)
						{
							this.parent.ShowDebugDetails.ShowPlayerDetails(i);
						}
					}
					else
					{
						this.parent.Reports.F12_0000_080d_ShowWondersOfTheWorldReport();
					}
					break;

				// F8 - Top 5 Cities
				case 0x4200:
					if (this.parent.Var_d806_DebugFlag)
					{
						this.parent.Reports.F12_0000_0573_ShowPowerGraphReport();
						this.parent.Replay.F9_0000_0000();
					}
					else
					{
						this.parent.HallOfFame.F3_0000_09ac_ShowTopFiveCitiesPopup();
					}
					break;

				// F9 - Civilization Score
				case 0x4300:
					if (this.parent.Var_d806_DebugFlag)
					{
						this.parent.Reports.F12_0000_03ac_ShowContinentStatisticReport();
					}
					else
					{
						this.parent.Overlay_20.F20_0000_0ca9_ShowCivilizationScorePopup(this.parent.GameData.HumanPlayerID, true);
					}
					break;

				// F10 - World Map
				case 0x4400:
					this.parent.Reports.F12_0000_0000_ShowWorldMapReport();
					break;

				// Shift + Home - Move Map
				case 0x4737:
					direction = this.parent.MoveDirections[8];
					this.parent.Var_d4cc_MapViewX += direction.X * 4;
					this.parent.Var_d75e_MapViewY += direction.Y * 4;

					// Instruction address 0x1403:0x3506, size: 5
					DrawVisibleMapWithPresentation(
						presentationLease,
						this.parent.GameData.HumanPlayerID,
						unitID,
						this.parent.Var_d4cc_MapViewX,
						this.parent.Var_d75e_MapViewY);
					break;

				// Shift + Up - Move Map
				case 0x4838:
					direction = this.parent.MoveDirections[1];
					this.parent.Var_d4cc_MapViewX += direction.X * 4;
					this.parent.Var_d75e_MapViewY += direction.Y * 4;

					// Instruction address 0x1403:0x3506, size: 5
					DrawVisibleMapWithPresentation(
						presentationLease,
						this.parent.GameData.HumanPlayerID,
						unitID,
						this.parent.Var_d4cc_MapViewX,
						this.parent.Var_d75e_MapViewY);
					break;

				// Shift + PageUp - Move Map
				case 0x4939:
					direction = this.parent.MoveDirections[2];
					this.parent.Var_d4cc_MapViewX += direction.X * 4;
					this.parent.Var_d75e_MapViewY += direction.Y * 4;

					// Instruction address 0x1403:0x3506, size: 5
					DrawVisibleMapWithPresentation(
						presentationLease,
						this.parent.GameData.HumanPlayerID,
						unitID,
						this.parent.Var_d4cc_MapViewX,
						this.parent.Var_d75e_MapViewY);
					break;

				// Shift + Left - Move Map
				case 0x4b34:
					direction = this.parent.MoveDirections[7];
					this.parent.Var_d4cc_MapViewX += direction.X * 4;
					this.parent.Var_d75e_MapViewY += direction.Y * 4;

					// Instruction address 0x1403:0x3506, size: 5
					DrawVisibleMapWithPresentation(
						presentationLease,
						this.parent.GameData.HumanPlayerID,
						unitID,
						this.parent.Var_d4cc_MapViewX,
						this.parent.Var_d75e_MapViewY);
					break;

				// Shift + Right - Move Map
				case 0x4d36:
					direction = this.parent.MoveDirections[3];
					this.parent.Var_d4cc_MapViewX += direction.X * 4;
					this.parent.Var_d75e_MapViewY += direction.Y * 4;

					// Instruction address 0x1403:0x3506, size: 5
					DrawVisibleMapWithPresentation(
						presentationLease,
						this.parent.GameData.HumanPlayerID,
						unitID,
						this.parent.Var_d4cc_MapViewX,
						this.parent.Var_d75e_MapViewY);
					break;

				// Shift + End - Move Map
				case 0x4f31:
					direction = this.parent.MoveDirections[6];
					this.parent.Var_d4cc_MapViewX += direction.X * 4;
					this.parent.Var_d75e_MapViewY += direction.Y * 4;

					// Instruction address 0x1403:0x3506, size: 5
					DrawVisibleMapWithPresentation(
						presentationLease,
						this.parent.GameData.HumanPlayerID,
						unitID,
						this.parent.Var_d4cc_MapViewX,
						this.parent.Var_d75e_MapViewY);
					break;

				// Shift + Down - Move Map
				case 0x5032:
					direction = this.parent.MoveDirections[5];
					this.parent.Var_d4cc_MapViewX += direction.X * 4;
					this.parent.Var_d75e_MapViewY += direction.Y * 4;

					// Instruction address 0x1403:0x3506, size: 5
					DrawVisibleMapWithPresentation(
						presentationLease,
						this.parent.GameData.HumanPlayerID,
						unitID,
						this.parent.Var_d4cc_MapViewX,
						this.parent.Var_d75e_MapViewY);
					break;

				// Shift + PageDown - Move Map
				case 0x5133:
					direction = this.parent.MoveDirections[4];
					this.parent.Var_d4cc_MapViewX += direction.X * 4;
					this.parent.Var_d75e_MapViewY += direction.Y * 4;

					// Instruction address 0x1403:0x3506, size: 5
					DrawVisibleMapWithPresentation(
						presentationLease,
						this.parent.GameData.HumanPlayerID,
						unitID,
						this.parent.Var_d4cc_MapViewX,
						this.parent.Var_d75e_MapViewY);
					break;
			}

		Label722:
			if (spentManualSelectionQolOnly &&
				selectingRoadToCityTarget)
			{
				goto Label79;
			}

			if (unitID < 128 && (unitID == -1 || this.parent.GameData.Players[playerID].Units[unitID].RemainingMoves > 0) &&
				!flag7 && this.parent.Var_dc48_GameEndType == 0) goto Label59;

			if (unitID < 128)
			{
				if (unitID != -1 && this.parent.GameData.Players[playerID].Units[unitID].UnitType != UnitTypeEnum.None)
				{
					if (this.parent.GameData.Players[playerID].Units[unitID].RemainingMoves > 0)
					{
						flag2 = false;
					}
					else
					{
						if (this.parent.GameData.Units[(int)this.parent.GameData.Players[playerID].Units[unitID].UnitType].TurnsOutside != 0 &&
							!fuelProcessedThisTurn[unitID])
						{
							// Selecting an already completed air unit revisits this label,
							// but it does not complete another flight day.
							fuelProcessedThisTurn[unitID] = true;

							if (((int)this.parent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(
								this.parent.GameData.Players[playerID].Units[unitID].Position.X, this.parent.GameData.Players[playerID].Units[unitID].Position.Y) & 0x1) != 0 ||
								this.parent.UnitManagement.F0_1866_1331_CountUnitTypesInStack(playerID, unitID, UnitTypeEnum.Carrier) != 0)
							{
								this.parent.GameData.Players[playerID].Units[unitID].SpecialMoves =
									this.parent.GameData.Units[(int)this.parent.GameData.Players[playerID].Units[unitID].UnitType].TurnsOutside;
							}

							this.parent.GameData.Players[playerID].Units[unitID].SpecialMoves--;

							if (this.parent.GameData.Players[playerID].Units[unitID].SpecialMoves < 0)
							{
								// Instruction address 0x1403:0x3d5d, size: 5
								this.parent.UnitManagement.F0_1866_0f10_DeleteUnit(playerID, unitID);

								// Instruction address 0x1403:0x3d69, size: 5
								ShowWorldMapOverlayWithPresentation(
									presentationLease, playerID, unitID,
									() => this.parent.Help.F4_0000_03aa_ShowInstantWarningPopup("*FUEL"));
							}
						}

						if (this.parent.GameData.Players[playerID].Units[unitID].UnitType == UnitTypeEnum.Trireme &&
							playerID == this.parent.GameData.HumanPlayerID)
						{
							bool hasAdjacentLand = false;

							for (int i = 1; i < 9; i++)
							{
								direction = this.parent.MoveDirections[i];

								GPoint newPosition = this.parent.GameData.Players[playerID].Units[unitID].Position + direction;

								if (this.parent.MapManagement.ValidateMapCoordinates(newPosition) && 
									this.parent.MapManagement.GetTerrainType(newPosition) != TerrainTypeEnum.Water)
								{
									hasAdjacentLand = true;
									break;
								}
							}

							if (ClassicTriremeLossPolicy.ShouldSink(
								this.parent.GameData.AiProfile,
								this.UsesSmartEnhancements &&
									this.parent.Segment_1ade
										.F0_1ade_22b5_PlayerHasTechnology(
											playerID,
											TechnologyAdvanceEnum.Navigation),
								hasAdjacentLand,
								() =>
									this.parent.TriremeLossRollForTests?.Invoke() ??
									this.parent.CAPI.RNG.Next(2) != 0))
							{
								// Instruction address 0x1403:0x3e18, size: 5
								this.parent.UnitManagement.F0_1866_0f10_DeleteUnit(playerID, unitID);
								// Instruction address 0x1403:0x3e24, size: 5
								ShowWorldMapOverlayWithPresentation(
									presentationLease, playerID, unitID,
									() => this.parent.Help.F4_0000_03aa_ShowInstantWarningPopup("*TRIREME"));
							}
						}
					}
				}
			}
			else if ((this.parent.GameData.PlayerFlags & (0x1 << playerID)) != 0)
			{
				// Instruction address 0x1403:0x3e43, size: 5
				F0_1403_4060(playerID, unitID);
			}

			goto Label18;

		Label748:
			if (!flag2 && this.parent.Var_dc48_GameEndType == 0) goto Label17;

			if (this.parent.Var_dc48_GameEndType == 0 && (this.parent.GameData.PlayerFlags & (0x1 << playerID)) != 0 &&
				ShouldWaitForEndOfTurnConfirmation(flag5))
			{
				unitID = 128;
				flag2 = false;
				flag6 = true;
				goto Label54;
			}

		Label755:
			if (playerID == this.parent.GameData.HumanPlayerID)
			{
				ClearHumanGoToHoverPreview(
					presentationLease,
					playerID,
					refresh: false);
				SetActiveHumanGoToPathUnit(
					presentationLease,
					playerID,
					-1);

				// Instruction address 0x1403:0x3ec1, size: 5
				this.parent.Segment_1238.F0_1238_1bb2_FillRectangleWithShadow(0, 97, 80, 103);
			}
		}

		internal bool TryLoadGameFromPlayerTurn()
		{
			if (!this.UsesSmartEnhancements)
			{
				return false;
			}

			this.parent.Graphics.F0_VGA_07d8_DrawImage(
				this.parent.Var_aa_Screen0_Rectangle,
				0,
				0,
				320,
				200,
				this.parent.Var_19d4_Screen1_Rectangle,
				0,
				0);
			if (this.parent.LoadAndSave
					.F11_0000_0000_LoadGameDialog() != -1)
			{
				this.parent.RestartTurnAfterInGameLoad = true;
				return true;
			}

			this.parent.Graphics.F0_VGA_07d8_DrawImage(
				this.parent.Var_19d4_Screen1_Rectangle,
				0,
				0,
				320,
				200,
				this.parent.Var_aa_Screen0_Rectangle,
				0,
				0);
			return false;
		}

		private void SetActiveHumanGoToPathUnit(
			OpenCivOne.Presentation.ClassicRuntimePresentationState
				.ClassicRuntimeMutationLease presentationLease,
			int playerID,
			int unitID)
		{
			if (playerID != this.parent.GameData.HumanPlayerID)
			{
				return;
			}

			int selectedUnitID =
				unitID >= 0 &&
				unitID < this.parent.GameData.Players[playerID].Units.Length &&
				this.parent.GameData.Players[playerID].Units[unitID].UnitType !=
					UnitTypeEnum.None
					? unitID
					: -1;
			if (this.parent.ActiveHumanGoToPathUnitID ==
				selectedUnitID)
			{
				return;
			}

			this.parent.ActiveHumanGoToPathUnitID = selectedUnitID;
			RefreshActiveHumanGoToPathMap(
				presentationLease,
				playerID);
		}

		private void UpdateHumanGoToHoverPreview(
			OpenCivOne.Presentation.ClassicRuntimePresentationState
				.ClassicRuntimeMutationLease presentationLease,
			int playerID,
			int unitID,
			GPoint pointerPosition)
		{
			if (!UsesSmartEnhancements ||
				!this.parent.GameData.GameSettingFlags.ShowGoToPaths ||
				playerID != this.parent.GameData.HumanPlayerID ||
				pointerPosition.X < 80 ||
				pointerPosition.X >= 320 ||
				pointerPosition.Y < 8 ||
				pointerPosition.Y >= 200)
			{
				ClearHumanGoToHoverPreview(
					presentationLease,
					playerID,
					refresh: true);
				return;
			}

			GPoint destination = new(
				this.parent.MapManagement.AdjustXPosition(
					((pointerPosition.X - 80) / 16) +
						this.parent.Var_d4cc_MapViewX),
				((pointerPosition.Y - 8) / 16) +
					this.parent.Var_d75e_MapViewY);
			if (!this.parent.MapManagement
					.ValidateMapCoordinates(destination))
			{
				ClearHumanGoToHoverPreview(
					presentationLease,
					playerID,
					refresh: true);
				return;
			}

			if (this.parent.ActiveHumanGoToPreviewUnitID ==
					unitID &&
				this.parent.ActiveHumanGoToPreviewDestination ==
					destination)
			{
				return;
			}

			this.parent.ActiveHumanGoToPreviewUnitID = unitID;
			this.parent.ActiveHumanGoToPreviewDestination =
				destination;
			this.parent.ActiveHumanGoToPreviewPath =
				this.parent.UnitGoTo.BuildVisibleGoToPreview(
					playerID,
					unitID,
					destination);
			RefreshActiveHumanGoToPathMap(
				presentationLease,
				playerID,
				force: true);
		}

		private void ClearHumanGoToHoverPreview(
			OpenCivOne.Presentation.ClassicRuntimePresentationState
				.ClassicRuntimeMutationLease presentationLease,
			int playerID,
			bool refresh)
		{
			bool hadPreview =
				this.parent.ActiveHumanGoToPreviewUnitID >= 0;
			this.parent.ActiveHumanGoToPreviewUnitID = -1;
			this.parent.ActiveHumanGoToPreviewDestination =
				OpenCivOneGame.InvalidPosition;
			this.parent.ActiveHumanGoToPreviewPath =
				Array.Empty<GPoint>();
			if (hadPreview && refresh)
			{
				RefreshActiveHumanGoToPathMap(
					presentationLease,
					playerID,
					force: true);
			}
		}

		private void RefreshActiveHumanGoToPathMap(
			OpenCivOne.Presentation.ClassicRuntimePresentationState
				.ClassicRuntimeMutationLease presentationLease,
			int playerID,
			bool force = false)
		{
			if (UsesSmartEnhancements &&
				playerID == this.parent.GameData.HumanPlayerID &&
				(force ||
					this.parent.GameData.GameSettingFlags.ShowGoToPaths))
			{
				DrawVisibleMapWithPresentation(
					presentationLease,
					playerID,
					this.parent.ActiveHumanGoToPathUnitID,
					this.parent.Var_d4cc_MapViewX,
					this.parent.Var_d75e_MapViewY);
			}
		}

		private int ResolveRoadToCityTarget(
			int playerID,
			int mapX,
			int mapY)
		{
			int exactCityID =
				this.parent.Tools
					.F0_2dc4_00ba_GetCityByLocation(
						mapX,
						mapY);
			if (exactCityID >= 0)
			{
				City exactCity =
					this.parent.GameData.Cities[exactCityID];
				return exactCity.StatusFlag != byte.MaxValue &&
					exactCity.ActualSize > 0 &&
					exactCity.PlayerID == playerID
						? exactCityID
						: -1;
			}

			City[] ownedCities =
			[
				.. this.parent.GameData.Cities.Where(city =>
					city.StatusFlag != byte.MaxValue &&
					city.ActualSize > 0 &&
					city.PlayerID == playerID)
			];

			// City names are drawn one row below their map cell and may span
			// several cells. Accept the complete visible label instead of
			// turning a valid city click into a misleading "no route" error.
			int labelCityID = ownedCities
				.Where(city =>
					IsRoadTargetCityLabelCell(city, mapX, mapY))
				.OrderBy(city =>
					this.parent.Tools
						.F0_2dc4_0289_GetShortestDistance(
							new GPoint(mapX, mapY),
							city.Position))
				.ThenBy(city => city.ID)
				.Select(city => city.ID)
				.DefaultIfEmpty(-1)
				.First();
			if (labelCityID >= 0)
			{
				return labelCityID;
			}

			// Retain the forgiving one-cell selection around the city icon.
			return ownedCities
				.Where(city =>
					city.StatusFlag != byte.MaxValue)
				.Select(city => new
				{
					city.ID,
					Distance = this.parent.Tools
						.F0_2dc4_0289_GetShortestDistance(
							new GPoint(mapX, mapY),
							city.Position)
				})
				.Where(candidate => candidate.Distance == 1)
				.OrderBy(candidate => candidate.ID)
				.Select(candidate => candidate.ID)
				.DefaultIfEmpty(-1)
				.First();
		}

		private int ResolveRoadToCityVisualTarget(
			int playerID,
			int mapX,
			int mapY,
			int screenX,
			int screenY)
		{
			int visualCityID = this.parent.GameData.Cities
				.Where(city =>
					city.StatusFlag != byte.MaxValue &&
					city.ActualSize > 0 &&
					city.PlayerID == playerID &&
					IsRoadTargetCityVisualHit(
						city,
						screenX,
						screenY))
				.Select(city => new
				{
					city.ID,
					Distance =
						GetRoadTargetCityVisualDistance(
							city,
							screenX,
							screenY)
				})
				.OrderBy(candidate => candidate.Distance)
				.ThenBy(candidate => candidate.ID)
				.Select(candidate => candidate.ID)
				.DefaultIfEmpty(-1)
				.First();

			return visualCityID >= 0
				? visualCityID
				: ResolveRoadToCityTarget(
					playerID,
					mapX,
					mapY);
		}

		private bool IsRoadTargetCityVisualHit(
			City city,
			int screenX,
			int screenY)
		{
			const int padding = 3;
			int cityCellOffset =
				FindVisibleMapCellOffset(city.Position.X);
			int cityRowOffset =
				city.Position.Y -
					this.parent.Var_d75e_MapViewY;
			if (cityCellOffset < 0 ||
				cityRowOffset < 0 ||
				cityRowOffset >= 12)
			{
				return false;
			}

			int cityScreenX = 80 + (cityCellOffset * 16);
			int cityScreenY = 8 + (cityRowOffset * 16);
			if (screenX >= cityScreenX - padding &&
				screenX < cityScreenX + 16 + padding &&
				screenY >= cityScreenY - padding &&
				screenY < cityScreenY + 16 + padding)
			{
				return true;
			}

			if (cityScreenY >= 184)
			{
				return false;
			}

			string cityName =
				this.parent.LanguageTools
					.F0_2f4d_04f7_TrimStringToWidth(
						this.parent.Segment_2459
							.F0_2459_08c6_GetCityName(city.ID),
						327 - cityScreenX);
			GSize labelSize =
				this.parent.Graphics.GetDrawStringSize(
					1,
					cityName);
			int labelStartX =
				this.parent.Tools
					.F0_2dc4_007c_CheckValueRange(
						cityScreenX - 8,
						80,
						999);
			int labelStartY = cityScreenY + 16;
			return screenX >= labelStartX - padding &&
				screenX < labelStartX + labelSize.Width + padding &&
				screenY >= labelStartY - padding &&
				screenY <
					labelStartY + labelSize.Height + 1 + padding;
		}

		private int GetRoadTargetCityVisualDistance(
			City city,
			int screenX,
			int screenY)
		{
			int cityCellOffset =
				FindVisibleMapCellOffset(city.Position.X);
			int cityRowOffset =
				city.Position.Y -
					this.parent.Var_d75e_MapViewY;
			int deltaX =
				screenX - (80 + (cityCellOffset * 16) + 8);
			int deltaY =
				screenY - (8 + (cityRowOffset * 16) + 8);
			return (deltaX * deltaX) + (deltaY * deltaY);
		}

		private bool IsRoadTargetCityLabelCell(
			City city,
			int mapX,
			int mapY)
		{
			if (mapY != city.Position.Y + 1)
			{
				return false;
			}

			int cityCellOffset =
				FindVisibleMapCellOffset(city.Position.X);
			int targetCellOffset =
				FindVisibleMapCellOffset(mapX);
			int cityRowOffset =
				city.Position.Y -
					this.parent.Var_d75e_MapViewY;
			if (cityCellOffset < 0 ||
				targetCellOffset < 0 ||
				cityRowOffset < 0 ||
				cityRowOffset > 10)
			{
				return false;
			}

			string cityName = this.parent.Segment_2459
				.F0_2459_08c6_GetCityName(city.ID);
			int cityScreenX = 80 + (cityCellOffset * 16);
			int maximumWidth = 327 - cityScreenX;
			while (cityName.Length > 1 &&
				this.parent.Graphics.GetDrawStringSize(
					1,
					cityName).Width > maximumWidth)
			{
				if (cityName[cityName.Length - 2] != ' ')
				{
					cityName =
						cityName.Substring(
							0,
							cityName.Length - 2) + ".";
				}
				else
				{
					cityName =
						cityName.Substring(
							0,
							cityName.Length - 1);
				}
			}

			int labelStartX = Math.Max(cityScreenX - 8, 80);
			int labelEndX = labelStartX +
				this.parent.Graphics.GetDrawStringSize(
					1,
					cityName).Width;
			int targetCellStartX =
				80 + (targetCellOffset * 16);
			int targetCellEndX =
				targetCellStartX + 16;
			return targetCellStartX < labelEndX &&
				targetCellEndX > labelStartX;
		}

		private int FindVisibleMapCellOffset(int mapX)
		{
			for (int offset = 0; offset < 15; offset++)
			{
				if (this.parent.MapManagement.AdjustXPosition(
						this.parent.Var_d4cc_MapViewX + offset) ==
					mapX)
				{
					return offset;
				}
			}

			return -1;
		}

		private bool TryPrepareRoadToCityAction(
			OpenCivOne.Presentation.ClassicRuntimePresentationState
				.ClassicRuntimeMutationLease presentationLease,
			int playerID,
			int unitID,
			bool startRequested,
			int? destinationCityID,
			out int command)
		{
			command = 0;
			bool hadOrder =
				this.parent.UnitAutomationState.TryGetOrder(
					this.parent.GameData,
					playerID,
					unitID,
					ClassicUnitAutomationKind.BuildRoadToCity,
					out ClassicUnitAutomationOrderMetadata order);
			if (!startRequested && !hadOrder)
			{
				return false;
			}

			if (!startRequested &&
				TryInterruptUnitAutomationForPendingManualInput(
					playerID,
					unitID,
					out _))
			{
				return false;
			}

			int selectedCityID = startRequested
				? destinationCityID ?? -1
				: order.DestinationCityID ?? -1;
			Unit settler =
				this.parent.GameData.Players[playerID].Units[unitID];
			ClassicRoadToCityPlan plan =
				ClassicRoadToCityPlanner.PlanNextAction(
					this.parent.GameData,
					this.parent.MapManagement,
					playerID,
					settler,
					selectedCityID);

			if (plan.Decision ==
				ClassicRoadToCityDecision.Complete)
			{
				this.parent.UnitAutomationState.Cancel(
					playerID,
					unitID);
				ShowWorldMapDialogWithPresentation(
					presentationLease,
					playerID,
					unitID,
					ClassicGameText.Current[
						ClassicGameTextKey.RoadToCityComplete],
					100,
					80);
				return false;
			}

			if (plan.Decision ==
				ClassicRoadToCityDecision.Ineligible)
			{
				this.parent.UnitAutomationState.Cancel(
					playerID,
					unitID);
				if (hadOrder || startRequested)
				{
					ShowWorldMapDialogWithPresentation(
						presentationLease,
						playerID,
						unitID,
						ClassicGameText.Current[
							ClassicGameTextKey.RoadToCityUnavailable],
						100,
						80);
				}
				return false;
			}

			bool buildCurrentCell =
				plan.Decision ==
					ClassicRoadToCityDecision
						.BuildRoadOnCurrentCell;
			GPoint target = buildCurrentCell
				? settler.Position
				: plan.NextPosition;
			ClassicUnitAutomationPhase phase = buildCurrentCell
				? ClassicUnitAutomationPhase.WorkingTarget
				: ClassicUnitAutomationPhase.MovingToTarget;
			if (!this.parent.UnitAutomationState.TrySetOrder(
				this.parent.GameData,
				playerID,
				unitID,
				ClassicUnitAutomationKind.BuildRoadToCity,
				phase,
				destinationCityID: selectedCityID,
				targetX: target.X,
				targetY: target.Y,
				workKind: ClassicUnitAutomationWorkKind.Road))
			{
				this.parent.UnitAutomationState.Cancel(
					playerID,
					unitID);
				return false;
			}

			ClearUnitGoTo(settler);
			ClearUnitWorkStatus(settler);
			if (startRequested && settler.RemainingMoves <= 0)
			{
				return false;
			}
			if (buildCurrentCell)
			{
				command = 'r';
				return true;
			}

			if (plan.Direction is < 1 or > 8)
			{
				this.parent.UnitAutomationState.Cancel(
					playerID,
					unitID);
				return false;
			}

			command = plan.Direction;
			return true;
		}

		private bool TryPrepareImproveNearestCityAction(
			OpenCivOne.Presentation.ClassicRuntimePresentationState
				.ClassicRuntimeMutationLease presentationLease,
			int playerID,
			int unitID,
			bool startRequested,
			out int command)
		{
			command = 0;
			bool hadOrder =
				this.parent.UnitAutomationState.TryGetOrder(
					this.parent.GameData,
					playerID,
					unitID,
					ClassicUnitAutomationKind.ImproveNearestCity,
					out _);
			if (!startRequested && !hadOrder)
			{
				return false;
			}

			if (!startRequested &&
				TryInterruptUnitAutomationForPendingManualInput(
					playerID,
					unitID,
					out _))
			{
				return false;
			}

			Unit settler =
				this.parent.GameData.Players[playerID].Units[unitID];
			ClassicImproveNearestCityPlan plan =
				ClassicImproveNearestCityPlanner.Plan(
					this.parent.GameData,
					this.parent.MapManagement,
					playerID,
					settler,
					reservedTargets:
						GetReservedImproveNearestCityTargets(
							playerID,
							unitID));
			if (plan.Decision !=
					ClassicImproveNearestCityDecision.Work ||
				plan.CityID < 0 ||
				plan.WorkKind is null)
			{
				this.parent.UnitAutomationState.Cancel(
					playerID,
					unitID);
				if (plan.Decision ==
						ClassicImproveNearestCityDecision.NoKnownNeed &&
					(hadOrder || startRequested))
				{
					ShowWorldMapDialogWithPresentation(
						presentationLease,
						playerID,
						unitID,
						ClassicGameText.Current[
							ClassicGameTextKey.ImproveNearestCityComplete],
						100,
						80);
				}
				return false;
			}

			bool atTarget = settler.Position == plan.Target;
			ClassicUnitAutomationPhase phase = atTarget
				? ClassicUnitAutomationPhase.WorkingTarget
				: ClassicUnitAutomationPhase.MovingToTarget;
			if (!this.parent.UnitAutomationState.TrySetOrder(
				this.parent.GameData,
				playerID,
				unitID,
				ClassicUnitAutomationKind.ImproveNearestCity,
				phase,
				destinationCityID: plan.CityID,
				targetX: plan.Target.X,
				targetY: plan.Target.Y,
				workKind: plan.WorkKind))
			{
				this.parent.UnitAutomationState.Cancel(
					playerID,
					unitID);
				return false;
			}

			ClearUnitGoTo(settler);
			ClearUnitWorkStatus(settler);
			if (!atTarget)
			{
				settler.GoToDestination = plan.Target;
				if (startRequested && settler.RemainingMoves <= 0)
				{
					return false;
				}
				return true;
			}

			if (startRequested && settler.RemainingMoves <= 0)
			{
				return false;
			}

			command = plan.WorkKind.Value switch
			{
				ClassicUnitAutomationWorkKind.Road => 'r',
				ClassicUnitAutomationWorkKind.Irrigation => 'i',
				ClassicUnitAutomationWorkKind.Mine => 'm',
				ClassicUnitAutomationWorkKind.Pollution => 'p',
				_ => 0
			};
			if (command != 0)
			{
				return true;
			}

			this.parent.UnitAutomationState.Cancel(
				playerID,
				unitID);
			return false;
		}

		private IReadOnlySet<GPoint>
			GetReservedImproveNearestCityTargets(
				int playerID,
				int currentUnitID)
		{
			HashSet<GPoint> reservedTargets = [];
			foreach (ClassicUnitAutomationOrderMetadata candidate in
				this.parent.UnitAutomationState.Orders)
			{
				if (candidate.PlayerID != playerID ||
					candidate.UnitID == currentUnitID ||
					candidate.Kind !=
						ClassicUnitAutomationKind.ImproveNearestCity ||
					candidate.TargetX is null ||
					candidate.TargetY is null ||
					!this.parent.UnitAutomationState.TryGetOrder(
						this.parent.GameData,
						playerID,
						candidate.UnitID,
						ClassicUnitAutomationKind.ImproveNearestCity,
						out _))
				{
					continue;
				}

				reservedTargets.Add(
					new GPoint(
						candidate.TargetX.Value,
						candidate.TargetY.Value));
			}

			return reservedTargets;
		}

		private static void ClearUnitGoTo(Unit unit)
		{
			unit.GoToDestination =
				OpenCivOneGame.InvalidPosition;
			unit.GoToPath.Clear();
			unit.GoToNextDirection = -1;
		}

		private bool ShouldPreserveSmartAiTransportGoToWait(
			int playerID,
			int unitID,
			int command)
		{
			if (!UsesSmartEnhancements ||
				playerID == this.parent.GameData.HumanPlayerID ||
				command != ' ' ||
				unitID < 0 ||
				unitID >= 128)
			{
				return false;
			}

			Player player =
				this.parent.GameData.Players[playerID];
			Unit transport = player.Units[unitID];
			if (transport.UnitType != UnitTypeEnum.Trireme ||
				transport.GoToDestination ==
					OpenCivOneGame.InvalidPosition ||
				transport.GoToPath.Count == 0 ||
				this.parent.Segment_1ade
					.F0_1ade_22b5_PlayerHasTechnology(
						playerID,
						TechnologyAdvanceEnum.Navigation))
			{
				return false;
			}

			short coastalRestThreshold =
				(short)((this.parent.GameData.Units[
					(int)transport.UnitType].MoveCount / 2) * 3);
			return transport.RemainingMoves <= coastalRestThreshold &&
				TransportStackContainsRole(
					player,
					transport,
					UnitRoleTypeEnum.Settler) &&
				TransportStackContainsRole(
					player,
					transport,
					UnitRoleTypeEnum.Defense);
		}

		private bool TransportStackContainsRole(
			Player player,
			Unit transport,
			UnitRoleTypeEnum role)
		{
			bool[] visited = new bool[player.Units.Length];
			int candidateID = transport.NextUnitID;
			while (candidateID >= 0 &&
				candidateID < player.Units.Length &&
				!visited[candidateID])
			{
				visited[candidateID] = true;
				if (candidateID == transport.ID)
				{
					break;
				}

				Unit candidate = player.Units[candidateID];
				if (candidate.UnitType != UnitTypeEnum.None &&
					candidate.Position == transport.Position &&
					this.parent.GameData.Units[
						(int)candidate.UnitType].MovementType ==
						UnitMovementTypeEnum.Land &&
					this.parent.GameData.Units[
						(int)candidate.UnitType].UnitRoleType ==
						role)
				{
					return true;
				}

				candidateID = candidate.NextUnitID;
			}

			return false;
		}

		private static void ClearUnitWorkStatus(Unit unit)
		{
			unit.ClearStatusFlags(
				UnitStatusEnum.SettlerBuildRoadOrRail |
					UnitStatusEnum.SettlerBuildIrrigation |
					UnitStatusEnum.SettlerBuildMineOrForest |
					UnitStatusEnum.SettlerCleanPollution);
			unit.SpecialMoves = 0;
		}

		private bool TryPrepareAutomaticExploreMove(
			int playerID,
			int unitID,
			out int command,
			out AutomaticExploreObservation? observation)
		{
			command = 0;
			observation = null;

			if (!this.parent.UnitAutomationState.TryGetOrder(
				this.parent.GameData,
				playerID,
				unitID,
				ClassicUnitAutomationKind.AutomaticExplore,
				out _))
			{
				this.automaticExploreProgress.Remove((playerID, unitID));
				return false;
			}

			if (TryInterruptUnitAutomationForPendingManualInput(
				playerID,
				unitID,
				out _))
			{
				return false;
			}

			Unit unit =
				this.parent.GameData.Players[playerID].Units[unitID];
			if (HasNearbyAutomaticExploreDecision(playerID, unit) ||
				HasEmbarkedLandCargo(playerID, unit))
			{
				this.parent.UnitAutomationState.Cancel(playerID, unitID);
				this.automaticExploreProgress.Remove((playerID, unitID));
				return false;
			}

			ClassicAutomaticExplorePlan plan =
				ClassicAutomaticExplorePlanner.PlanNextMove(
					this.parent.GameData,
					this.parent.MapManagement,
					playerID,
					unit);
			if (IsUnproductiveAutomaticExploreReversal(
				playerID,
				unitID,
				unit,
				plan))
			{
				this.parent.UnitAutomationState.Cancel(playerID, unitID);
				this.automaticExploreProgress.Remove((playerID, unitID));
				this.parent.Host.ShowTransientStatus(
					ClassicGameText.Current[
						ClassicGameTextKey
							.AutomaticExploreNoSafeCoastalRoute]);
				return false;
			}

			if (plan.Decision !=
					ClassicAutomaticExploreDecision.Move ||
				plan.Direction < 1 ||
				plan.Direction > 8 ||
				IsUnsafeFinalTriremeMove(
					playerID,
					unit,
					plan.Direction))
			{
				this.parent.UnitAutomationState.Cancel(playerID, unitID);
				this.automaticExploreProgress.Remove((playerID, unitID));
				if (unit.UnitType == UnitTypeEnum.Trireme &&
					plan.Decision ==
						ClassicAutomaticExploreDecision.NoKnownFrontier)
				{
					this.parent.Host.ShowTransientStatus(
						ClassicGameText.Current[
							ClassicGameTextKey
								.AutomaticExploreNoSafeCoastalRoute]);
				}
				return false;
			}

			observation = CaptureAutomaticExploreObservation(
				playerID,
				unit.Position);
			if (!this.parent.UnitAutomationState.TrySetOrder(
				this.parent.GameData,
				playerID,
				unitID,
				ClassicUnitAutomationKind.AutomaticExplore,
				ClassicUnitAutomationPhase.MovingToTarget,
				targetX: plan.Target.X,
				targetY: plan.Target.Y))
			{
				this.parent.UnitAutomationState.Cancel(playerID, unitID);
				this.automaticExploreProgress.Remove((playerID, unitID));
				observation = null;
				return false;
			}

			command = plan.Direction;
			return true;
		}

		private bool TryStartAutomaticExploreMove(
			int playerID,
			int unitID,
			out int command,
			out AutomaticExploreObservation? observation)
		{
			command = 0;
			observation = null;
			this.automaticExploreProgress.Remove((playerID, unitID));

			if (!this.parent.UnitAutomationState.TrySetOrder(
				this.parent.GameData,
				playerID,
				unitID,
				ClassicUnitAutomationKind.AutomaticExplore,
				ClassicUnitAutomationPhase.SelectingTarget))
			{
				return false;
			}

			Unit unit =
				this.parent.GameData.Players[playerID].Units[unitID];
			ClearUnitGoTo(unit);
			if (unit.RemainingMoves <= 0)
			{
				return false;
			}

			return TryPrepareAutomaticExploreMove(
				playerID,
				unitID,
				out command,
				out observation);
		}

		private bool TryHandleAutomaticExploreShortcut(
			int playerID,
			int unitID,
			bool interruptedByManualInput,
			out int command,
			out AutomaticExploreObservation? observation)
		{
			command = 0;
			observation = null;
			if (interruptedByManualInput)
			{
				return false;
			}

			return TryStartAutomaticExploreMove(
				playerID,
				unitID,
				out command,
				out observation);
		}

		private void ExecuteMoveUnit(
			int playerID,
			Unit? unit,
			int direction,
			ref int unitMoveCount,
			bool automaticExploreMove,
			AutomaticExploreObservation? observation)
		{
			using OpenCivOne.Presentation.ClassicRuntimePresentationState
				.ClassicRuntimeMutationLease presentationLease =
					this.parent.PresentationState.EnterRuntimeMutation();

			ExecuteMoveUnitWithPresentation(
				presentationLease,
				playerID,
				unit,
				direction,
				ref unitMoveCount,
				automaticExploreMove,
				observation);
		}

		private void ExecuteMoveUnitWithPresentation(
			OpenCivOne.Presentation.ClassicRuntimePresentationState
				.ClassicRuntimeMutationLease presentationLease,
			int playerID,
			Unit? unit,
			int direction,
			ref int unitMoveCount,
			bool automaticExploreMove,
			AutomaticExploreObservation? observation)
		{
			int unitID = unit?.ID ?? -1;
			GPoint origin = unit?.Position ?? OpenCivOneGame.InvalidPosition;

			MoveUnitWithPresentation(
				presentationLease,
				playerID,
				unit,
				direction,
				ref unitMoveCount);

			if (!automaticExploreMove ||
				unitID < 0 ||
				unitID >= 128)
			{
				return;
			}

			if (observation is null ||
				unit is null ||
				unit.UnitType == UnitTypeEnum.None ||
				unit.ID != unitID ||
				unit.Position == origin ||
				ShouldStopAutomaticExploreAfterMove(
					playerID,
					unit,
					observation))
			{
				this.parent.UnitAutomationState.Cancel(playerID, unitID);
				this.automaticExploreProgress.Remove((playerID, unitID));
				return;
			}

			if (!this.parent.UnitAutomationState.TrySetOrder(
				this.parent.GameData,
				playerID,
				unitID,
				ClassicUnitAutomationKind.AutomaticExplore,
				ClassicUnitAutomationPhase.SelectingTarget))
			{
				this.parent.UnitAutomationState.Cancel(playerID, unitID);
				this.automaticExploreProgress.Remove((playerID, unitID));
				return;
			}

			this.automaticExploreProgress[(playerID, unitID)] =
				new AutomaticExploreProgress(
					unit,
					origin,
					unit.Position,
					CountKnownCells(playerID) >
						observation.KnownCellCount);
		}

		internal void CompleteManualPointerSelection()
		{
			if (!UsesSmartEnhancements)
			{
				this.parent.CommonTools
					.ClearKeyboardEventsAndEnsureNoMouseButtonIsPressed();
				return;
			}

			// The original loop discarded every queued key after handling
			// a pointer selection. On modern hosts a quick E/V/X press can
			// arrive while the release event of the preceding click is still
			// queued, making the command appear to do nothing. Keep
			// intentional keyboard input in 1991+ and only finish draining
			// the pointer gesture. The next input cycle applies the command
			// to the unit selected by that gesture.
			while (this.parent.GetMouseEvent().Buttons !=
				MouseButtonsEnum.None)
			{
				Thread.Sleep(1);
			}
		}

		private bool HasPendingManualInput()
		{
			if (this.parent.CAPI.kbhit() != 0)
			{
				return true;
			}

			lock (OpenCivOneGame.KeyboardAndMouseLock)
			{
				return this.parent.MouseEvents.Any(
					static mouseEvent =>
						mouseEvent.Buttons !=
							MouseButtonsEnum.None);
			}
		}

		private bool TryInterruptUnitAutomationForPendingManualInput(
			int playerID,
			int unitID,
			out ClassicUnitAutomationKind interruptedKind)
		{
			interruptedKind =
				ClassicUnitAutomationKind.AutomaticExplore;
			if (!HasPendingManualInput())
			{
				return false;
			}

			return TryCancelUnitAutomationForManualControl(
				playerID,
				unitID,
				out interruptedKind);
		}

		private bool TryCancelUnitAutomationForManualControl(
			int playerID,
			int unitID,
			out ClassicUnitAutomationKind interruptedKind)
		{
			interruptedKind =
				ClassicUnitAutomationKind.AutomaticExplore;
			ClassicUnitAutomationOrderMetadata? order = null;
			foreach (ClassicUnitAutomationKind kind in
				new[]
				{
					ClassicUnitAutomationKind.AutomaticExplore,
					ClassicUnitAutomationKind.ImproveNearestCity,
					ClassicUnitAutomationKind.BuildRoadToCity
				})
			{
				if (this.parent.UnitAutomationState.TryGetOrder(
					this.parent.GameData,
					playerID,
					unitID,
					kind,
					out ClassicUnitAutomationOrderMetadata candidate))
				{
					interruptedKind = kind;
					order = candidate;
					break;
				}
			}

			if (order is null ||
				!this.parent.UnitAutomationState.Cancel(
					playerID,
					unitID))
			{
				return false;
			}

			this.automaticExploreProgress.Remove((playerID, unitID));

			Unit unit =
				this.parent.GameData.Players[playerID].Units[unitID];
			unit.GoToDestination = OpenCivOneGame.InvalidPosition;
			unit.GoToNextDirection = -1;
			switch (order.WorkKind)
			{
				case ClassicUnitAutomationWorkKind.Road:
					unit.ClearStatusFlags(
						UnitStatusEnum.SettlerBuildRoadOrRail);
					break;
				case ClassicUnitAutomationWorkKind.Irrigation:
					unit.ClearStatusFlags(
						UnitStatusEnum.SettlerBuildIrrigation);
					break;
				case ClassicUnitAutomationWorkKind.Mine:
					unit.ClearStatusFlags(
						UnitStatusEnum.SettlerBuildMineOrForest);
					break;
				case ClassicUnitAutomationWorkKind.Pollution:
					unit.ClearStatusFlags(
						UnitStatusEnum.SettlerCleanPollution);
					break;
			}

			return true;
		}

		private bool HasEmbarkedLandCargo(
			int playerID,
			Unit unit)
		{
			UnitDefinition definition =
				this.parent.GameData.Units[(int)unit.UnitType];
			return definition.MovementType ==
					UnitMovementTypeEnum.Water &&
				definition.TransportCapacity > 0 &&
				GetEmbarkedLandCargoUnitIDs(
					playerID,
					unit.ID,
					unit.Position).Length > 0;
		}

		private bool IsUnsafeFinalTriremeMove(
			int playerID,
			Unit unit,
			int direction)
		{
			if (unit.UnitType != UnitTypeEnum.Trireme ||
				unit.RemainingMoves > 3)
			{
				return false;
			}

			GPoint offset = this.parent.MoveDirections[direction];
			int destinationY = unit.Position.Y + offset.Y;
			int destinationX =
				this.parent.MapManagement.AdjustXPosition(
					unit.Position.X + offset.X);
			if (destinationY < 0 ||
				destinationY >=
					this.parent.GameData.MapVisibility.GetLength(1))
			{
				return true;
			}

			return !HasKnownAdjacentLand(
				playerID,
				new GPoint(destinationX, destinationY));
		}

		private bool HasKnownAdjacentLand(
			int playerID,
			GPoint position)
		{
			ushort visibilityMask = (ushort)(1 << playerID);
			int height =
				this.parent.GameData.MapVisibility.GetLength(1);

			for (int direction = 1; direction <= 8; direction++)
			{
				GPoint offset = this.parent.MoveDirections[direction];
				int y = position.Y + offset.Y;
				if (y < 0 || y >= height)
				{
					continue;
				}

				int x = this.parent.MapManagement.AdjustXPosition(
					position.X + offset.X);
				if ((this.parent.GameData.MapVisibility[x, y] &
						visibilityMask) == 0)
				{
					continue;
				}

				if (this.parent.MapManagement.GetTerrainType(x, y) !=
					TerrainTypeEnum.Water)
				{
					return true;
				}
			}

			return false;
		}

		private AutomaticExploreObservation
			CaptureAutomaticExploreObservation(
				int playerID,
				GPoint position)
		{
			return new AutomaticExploreObservation(
				position,
				CountKnownCells(playerID));
		}

		private int CountKnownCells(int playerID)
		{
			ushort visibilityMask = (ushort)(1 << playerID);
			int width =
				this.parent.GameData.MapVisibility.GetLength(0);
			int height =
				this.parent.GameData.MapVisibility.GetLength(1);
			int count = 0;
			for (int y = 0; y < height; y++)
			{
				for (int x = 0; x < width; x++)
				{
					if ((this.parent.GameData.MapVisibility[x, y] &
						visibilityMask) != 0)
					{
						count++;
					}
				}
			}

			return count;
		}

		private bool IsUnproductiveAutomaticExploreReversal(
			int playerID,
			int unitID,
			Unit unit,
			ClassicAutomaticExplorePlan plan)
		{
			if (unit.UnitType != UnitTypeEnum.Trireme ||
				plan.Decision !=
					ClassicAutomaticExploreDecision.Move ||
				plan.Direction is < 1 or > 8 ||
				!this.automaticExploreProgress.TryGetValue(
					(playerID, unitID),
					out AutomaticExploreProgress? progress))
			{
				return false;
			}

			if (!ReferenceEquals(progress.Unit, unit) ||
				progress.CurrentPosition != unit.Position)
			{
				this.automaticExploreProgress.Remove(
					(playerID, unitID));
				return false;
			}

			if (progress.RevealedNewCells)
			{
				return false;
			}

			GPoint offset = this.parent.MoveDirections[plan.Direction];
			GPoint destination = new(
				this.parent.MapManagement.AdjustXPosition(
					unit.Position.X + offset.X),
				unit.Position.Y + offset.Y);
			return destination == progress.PreviousPosition;
		}

		private bool ShouldStopAutomaticExploreAfterMove(
			int playerID,
			Unit unit,
			AutomaticExploreObservation observation)
		{
			if (unit.Position == observation.Position ||
				HasNearbyAutomaticExploreDecision(playerID, unit))
			{
				return true;
			}

			// Discovering an ordinary coast is not a decision by itself.
			// Otherwise a land explorer on a small island stops after almost
			// every move and the persistent order appears broken. Huts,
			// foreign cities and nearby foreign units still stop the order.
			return false;
		}

		private bool HasNearbyAutomaticExploreDecision(
			int playerID,
			Unit unit)
		{
			UnitMovementTypeEnum movementType =
				this.parent.GameData.Units[(int)unit.UnitType]
					.MovementType;
			if (movementType == UnitMovementTypeEnum.Water)
			{
				// A ship on exploration duty keeps sailing after merely
				// sighting a foreign city or unit. The planner itself
				// excludes visible occupied cells, so this never turns
				// exploration into an automatic attack.
				return false;
			}

			ushort visibilityMask = (ushort)(1 << playerID);
			int height =
				this.parent.GameData.MapVisibility.GetLength(1);

			for (int yOffset = -1; yOffset <= 1; yOffset++)
			{
				int y = unit.Position.Y + yOffset;
				if (y < 0 || y >= height)
				{
					continue;
				}

				for (int xOffset = -1; xOffset <= 1; xOffset++)
				{
					int x =
						this.parent.MapManagement.AdjustXPosition(
							unit.Position.X + xOffset);
					if ((this.parent.GameData.MapVisibility[x, y] &
							visibilityMask) == 0)
					{
						continue;
					}

					TerrainTypeEnum terrain =
						this.parent.MapManagement.GetTerrainType(x, y);
					if (this.parent.MapManagement
							.F0_2aea_1894_CellHasMinorTribeHut(
								x,
								y,
								terrain))
					{
						return true;
					}

					TerrainImprovementFlagsEnum improvements =
						this.parent.MapManagement
							.F0_2aea_15c1_GetTerrainImprovements(
								x,
								y);
					if (improvements.HasFlag(
							TerrainImprovementFlagsEnum.City) &&
						!HasOwnCityAt(playerID, x, y))
					{
						return true;
					}
				}
			}

			foreach (int otherPlayerID in
				Enumerable.Range(
					0,
					this.parent.GameData.Players.Length))
			{
				if (otherPlayerID == playerID)
				{
					continue;
				}

				foreach (Unit otherUnit in
					this.parent.GameData.Players[otherPlayerID]
						.Units)
				{
					if ((otherUnit.VisibleByPlayer &
							visibilityMask) == 0 ||
						otherUnit.UnitType == UnitTypeEnum.None)
					{
						continue;
					}

					if (this.parent.Tools
							.F0_2dc4_0289_GetShortestDistance(
								unit.Position,
								otherUnit.Position) <= 1)
					{
						return true;
					}
				}
			}

			return false;
		}

		private bool HasOwnCityAt(
			int playerID,
			int x,
			int y)
		{
			foreach (City city in this.parent.GameData.Cities)
			{
				if (city.StatusFlag != byte.MaxValue &&
					city.PlayerID == playerID &&
					city.Position.X == x &&
					city.Position.Y == y)
				{
					return true;
				}
			}

			return false;
		}

		/// <summary>
		/// Moves the unit in the desired direction
		/// </summary>
		/// <param name="playerID"></param>
		/// <param name="unit"></param>
		/// <param name="newMoveDirection"></param>
		/// <param name="unitMoveCount"></param>
		private void MoveUnit(
			int playerID,
			Unit? unit,
			int newMoveDirection,
			ref int unitMoveCount)
		{
			using OpenCivOne.Presentation.ClassicRuntimePresentationState
				.ClassicRuntimeMutationLease presentationLease =
					this.parent.PresentationState.EnterRuntimeMutation();

			MoveUnitWithPresentation(
				presentationLease,
				playerID,
				unit,
				newMoveDirection,
				ref unitMoveCount);
		}

		private void MoveUnitWithPresentation(
			OpenCivOne.Presentation.ClassicRuntimePresentationState
				.ClassicRuntimeMutationLease presentationLease,
			int playerID,
			Unit? unit,
			int newMoveDirection,
			ref int unitMoveCount)
		{
			if (unit != null && unit.UnitType != UnitTypeEnum.None)
			{
				GPoint direction = this.parent.MoveDirections[newMoveDirection];

				if (this.parent.MapManagement.ValidateMapCoordinates(unit.Position + direction))
				{
					// Barbarian units (excluding diplomat units)
					if (playerID == 0 && unit.UnitType != UnitTypeEnum.Diplomat)
					{
						TerrainImprovementFlagsEnum terrainImprovements = this.parent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(unit.Position.X, unit.Position.Y);

						if (!terrainImprovements.HasFlag(TerrainImprovementFlagsEnum.City) &&
							(terrainImprovements.HasFlag(TerrainImprovementFlagsEnum.Mines) || terrainImprovements.HasFlag(TerrainImprovementFlagsEnum.Irrigation)) &&
							unit.UnitType != UnitTypeEnum.Legion && unit.UnitType != UnitTypeEnum.Knights &&
							this.parent.GameData.Cities[this.parent.Tools.F0_2dc4_0102_FindNearestCity(unit.Position.X, unit.Position.Y)].PlayerID == this.parent.GameData.HumanPlayerID)
						{
							// Instruction address 0x1403:0x1d35, size: 5
							this.parent.MapManagement.F0_2aea_16ee_ClearTerrainImprovements(unit.Position.X, unit.Position.Y, TerrainImprovementFlagsEnum.Mines | TerrainImprovementFlagsEnum.Irrigation);

							if ((this.parent.GameData.MapVisibility[unit.Position.X, unit.Position.Y] & (0x1 << this.parent.GameData.HumanPlayerID)) != 0)
							{
								// Instruction address 0x1403:0x1d68, size: 5
								this.parent.MapManagement.F0_2aea_1601_UpdateVisibleCellStatus(unit.Position.X, unit.Position.Y);
								// Instruction address 0x1403:0x1d76, size: 5
								DrawCellWithUnitWithPresentation(
									presentationLease,
									playerID,
									unit.ID,
									unit.Position.X,
									unit.Position.Y);
							}

							unit.RemainingMoves = 0;
							return;
						}
					}

					// current unit position
					TerrainTypeEnum currentTerrainType = this.parent.MapManagement.GetTerrainType(unit.Position);
					int unitID = unit.ID;

					// New unit position
					int newX = this.parent.MapManagement.AdjustXPosition(unit.Position.X + direction.X);
					int newY = unit.Position.Y + direction.Y;
					TerrainTypeEnum newTerrainType = this.parent.MapManagement.GetTerrainType(newX, newY);
					TerrainImprovementFlagsEnum newImprovements = this.parent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(newX, newY);
					int newActiveUnitID = this.parent.MapManagement.F0_2aea_1458_GetCellActiveUnitID(newX, newY);
					int newActiveUnitPlayerID = this.parent.MapManagement.F0_2aea_14e0_GetCellActiveUnitPlayerID(newX, newY);

					// Land unit movement for Diplomat or Caravan unit
					if (this.parent.GameData.Units[(int)unit.UnitType].MovementType == UnitMovementTypeEnum.Land)
					{
						// Check if there are enemy units nearby
						if (IsMovementBlockedByZoneOfControl(
								playerID,
								unit,
								currentTerrainType,
								newActiveUnitID,
								newX,
								newY))
						{
							if (playerID == this.parent.GameData.HumanPlayerID)
							{
								// Instruction address 0x1403:0x1e9c, size: 5
								this.parent.CommonTools.PlayTune(37, 0);

								if (this.parent.GameData.GameSettingFlags.InstantAdvice)
								{
									// Instruction address 0x1403:0x1eb2, size: 5
									ShowWorldMapOverlayWithPresentation(
										presentationLease, playerID, unitID,
										() => this.parent.Help.F4_0000_03aa_ShowInstantWarningPopup("*ZOC"));
								}
								else
								{
									this.parent.Host.ShowTransientStatus(
										ClassicShellText
											.ZoneOfControlMovementBlocked);
								}
							}

							unit.GoToDestination = OpenCivOneGame.InvalidPosition;

							return;
						}

						// Diplomat or Caravan unit
						if (unit.UnitType == UnitTypeEnum.Diplomat || unit.UnitType == UnitTypeEnum.Caravan)
						{
							int cityID = this.parent.Tools.F0_2dc4_00ba_GetCityByLocation(newX, newY);

							if (cityID != -1)
							{
								// Diplomat or Caravan unit interaction with a city

								if (currentTerrainType == TerrainTypeEnum.Water && this.parent.GameData.Cities[cityID].PlayerID != playerID)
									return;

								// Diplomat unit
								if (unit.UnitType == UnitTypeEnum.Diplomat && playerID != this.parent.GameData.Cities[cityID].PlayerID)
								{
									if (this.parent.GameData.HumanPlayerID == this.parent.GameData.Cities[cityID].PlayerID)
									{
										unit.VisibleByPlayer |= (ushort)(1 << this.parent.GameData.HumanPlayerID);

										// Instruction address 0x1403:0x1f7f, size: 5
										CenterMapWithPresentation(
											presentationLease,
											playerID,
											unitID,
											unit.Position.X,
											unit.Position.Y);
										// Instruction address 0x1403:0x1f8b, size: 5
										this.parent.CommonTools.WaitTimer(30);
										// Instruction address 0x1403:0x1f9c, size: 5
										AnimateUnitMoveWithPresentation(
											presentationLease,
											playerID,
											unitID,
											newMoveDirection);
									}

									this.parent.Overlay_22.F22_0000_0000_DiplomatActionOnACity(cityID, playerID, unitID);

									return;
								}

								// Caravan unit
								if (unit.UnitType == UnitTypeEnum.Caravan)
								{
									int distance = this.parent.Tools.F0_2dc4_0289_GetShortestDistance(
										newX, this.parent.GameData.Cities[unit.HomeCityID].Position.X,
										newY, this.parent.GameData.Cities[unit.HomeCityID].Position.Y);

									if (this.parent.GameData.Cities[cityID].PlayerID != playerID ||
										this.parent.GameData.Cities[cityID].CurrentProductionID < -24 || distance >= 10 ||
										this.parent.MapManagement.F0_2aea_1942_GetGroupID(newX, newY) != this.parent.MapManagement.F0_2aea_1942_GetGroupID(
											this.parent.GameData.Cities[unit.HomeCityID].Position.X, this.parent.GameData.Cities[unit.HomeCityID].Position.Y))
									{
										int selectedCaravanOption = 1;

										if (this.parent.GameData.Cities[cityID].PlayerID == playerID)
										{
											StringBuilder caravanOptions = new();
											caravanOptions.Append("Will you?\n Keep moving\n Establish trade route\n");

											if (this.parent.GameData.Cities[cityID].PlayerID == playerID && this.parent.GameData.Cities[cityID].CurrentProductionID < -24)
											{
												// Instruction address 0x1403:0x209d, size: 5
												caravanOptions.Append(" Help build WONDER.\n");

												if (distance < 10)
												{
													this.parent.Var_b276_MenuBoxDisabledOptions = 2;
												}
											}

											selectedCaravanOption = ShowWorldMapDialogWithPresentation(
												presentationLease,
												playerID,
												unitID,
												caravanOptions.ToString(),
												100,
												80);
										}

										if (selectedCaravanOption == 1)
										{
											this.parent.Segment_2459.F0_2459_0948_CaravanArrivesAtDestinationCity(playerID, unitID, cityID);

											return;
										}

										if (selectedCaravanOption == 2)
										{
											this.parent.GameData.Cities[cityID].ShieldsCount += (short)(10 * this.parent.GameData.Units[(int)unit.UnitType].Cost);

											// Instruction address 0x1403:0x2149, size: 5
											this.parent.UnitManagement.F0_1866_0f10_DeleteUnit(playerID, unitID);

											return;
										}
									}
								}
							}
							else if (unit.UnitType == UnitTypeEnum.Diplomat && newActiveUnitID != -1 && playerID != newActiveUnitPlayerID)
							{
								// Diplomat interaction with the unit
								this.parent.Overlay_22.F22_0000_0639_DiplomatInteractionWithUnit(newActiveUnitPlayerID, newActiveUnitID, playerID);

								unit.GoToDestination = OpenCivOneGame.InvalidPosition;
							}
						}
					}

					// Move land unit onto transport
					if (unit.UnitType != UnitTypeEnum.None && this.parent.GameData.Units[(int)unit.UnitType].MovementType == UnitMovementTypeEnum.Land &&
						newTerrainType == TerrainTypeEnum.Water)
					{
						if (playerID != newActiveUnitPlayerID || newActiveUnitID == -1 || 
							this.parent.UnitManagement.F0_1866_13d5_GetWaterTransportCapabilityCount(playerID, newActiveUnitID) <= 0)
						{
							if (playerID ==
								this.parent.GameData.HumanPlayerID)
							{
								this.parent.Host.ShowTransientStatus(
									ClassicShellText
										.LandUnitNeedsTransport);
							}

							return;
						}

						unit.Status |= UnitStatusEnum.Sentry;
						unit.ClearStatusFlags(UnitStatusEnum.Fortifying | UnitStatusEnum.Fortified);
						// !!! Why newly loaded unit has any remaining moves?
						unit.RemainingMoves = 3;
					}
					else if (newActiveUnitID != -1 && playerID != newActiveUnitPlayerID)
					{
						if (currentTerrainType == TerrainTypeEnum.Water && this.parent.GameData.Units[(int)unit.UnitType].MovementType == UnitMovementTypeEnum.Land)
						{
							if (playerID == this.parent.GameData.HumanPlayerID)
							{
								// Instruction address 0x1403:0x224c, size: 5
								ShowWorldMapOverlayWithPresentation(
									presentationLease, playerID, unitID,
									() => this.parent.Help.F4_0000_03aa_ShowInstantWarningPopup("*AMPHIB"));
							}

							unit.GoToDestination = OpenCivOneGame.InvalidPosition;

							return;
						}

						// Cases where an invalid turn is made
						if (unit.UnitType == UnitTypeEnum.Diplomat ||
							(newTerrainType != TerrainTypeEnum.Water && unit.UnitType == UnitTypeEnum.Submarine) ||
							(playerID != this.parent.GameData.HumanPlayerID && this.parent.GameData.Units[(int)unit.UnitType].AttackStrength == 0))
						{
							return;
						}

						// Case where we want to attack a air unit
						if (unit.UnitType != UnitTypeEnum.Fighter &&
							this.parent.GameData.Units[(int)this.parent.GameData.Players[newActiveUnitPlayerID].Units[newActiveUnitID].UnitType].MovementType == UnitMovementTypeEnum.Air)
						{
							if (!newImprovements.HasFlag(TerrainImprovementFlagsEnum.City))
							{
								// Only FIGHTER units may attack AIR units
								ShowWorldMapOverlayWithPresentation(
									presentationLease, playerID, unitID,
									() => this.parent.Help.F4_0000_03aa_ShowInstantWarningPopup("*FIGHTER"));

								unit.GoToDestination = OpenCivOneGame.InvalidPosition;

								return;
							}
						}

						if (unit.RemainingMoves < 3)
						{
							if (playerID == this.parent.GameData.HumanPlayerID)
							{
								if (!UsesSmartEnhancements &&
									ShowWorldMapDialogWithPresentation(
										presentationLease,
										playerID,
										unitID,
										$"Attack at\n{unit.RemainingMoves}/3 strength?\n Cancel\n Attack\n",
										100,
										16) != 1)
								{
									unit.GoToDestination = OpenCivOneGame.InvalidPosition;

									return;
								}
							}
							else
							{
								// AI player will cancel the attack if strength is diminished
								if (unit.RemainingMoves < 2) return;
							}
						}

						if (newActiveUnitPlayerID == this.parent.GameData.HumanPlayerID)
						{
							// Instruction address 0x1403:0x23eb, size: 5
							CenterMapWithPresentation(
								presentationLease,
								playerID,
								unitID,
								newX,
								newY);
						}

						newActiveUnitID = this.parent.UnitManagement.F0_1866_1122(newActiveUnitPlayerID, newActiveUnitID);

						if (playerID ==
								this.parent.GameData.HumanPlayerID &&
							ClassicCombatForecast.IsAvailable(
								this.parent.GameData.AiProfile,
								unit.UnitType))
						{
							ClassicCombatForecast forecast =
								this.parent.Segment_29f3
									.GetCombatForecast(
										playerID,
										unitID,
										newActiveUnitPlayerID,
										newActiveUnitID);
							string reducedStrength =
								unit.RemainingMoves < 3
									? ClassicGameText.Current.Format(
										ClassicGameTextKey
											.CombatPreviewReducedStrength,
										unit.RemainingMoves)
									: string.Empty;
							string previewPrompt =
								ClassicGameText.Current.Format(
									ClassicGameTextKey
										.CombatPreviewPrompt,
									forecast
										.ApproximateWinPercent,
									reducedStrength);
							if (ShowWorldMapDialogWithPresentation(
								presentationLease,
								playerID,
								unitID,
								previewPrompt,
								100,
								16) != 1)
							{
								unit.GoToDestination =
									OpenCivOneGame
										.InvalidPosition;
								return;
							}
						}

						ushort humanCombatVisibilityMask =
							(ushort)(0x1 << this.parent.GameData.HumanPlayerID);
						bool aiVersusAiCombat =
							playerID != this.parent.GameData.HumanPlayerID &&
							newActiveUnitPlayerID != this.parent.GameData.HumanPlayerID;
						Unit defendingUnit =
							this.parent.GameData.Players[newActiveUnitPlayerID].Units[newActiveUnitID];
						bool attackerCellKnownToHuman =
							(this.parent.GameData.MapVisibility[unit.Position.X, unit.Position.Y] &
								humanCombatVisibilityMask) != 0;
						bool defenderCellKnownToHuman =
							(this.parent.GameData.MapVisibility[defendingUnit.Position.X, defendingUnit.Position.Y] &
								humanCombatVisibilityMask) != 0;

						if (aiVersusAiCombat)
						{
							if (!attackerCellKnownToHuman)
							{
								unit.VisibleByPlayer &= (ushort)~humanCombatVisibilityMask;
							}

							if (!defenderCellKnownToHuman)
							{
								defendingUnit.VisibleByPlayer &= (ushort)~humanCombatVisibilityMask;
							}
						}

						if (playerID == this.parent.GameData.HumanPlayerID || newActiveUnitPlayerID == this.parent.GameData.HumanPlayerID)
						{
							this.parent.Var_70d8 = true;
						}

						int humanPlayerID =
							this.parent.GameData.HumanPlayerID;
						int attackResult = this.parent.Segment_29f3
							.F0_29f3_000e_AttackUnitWithPresentation(
								playerID,
								unitID,
								newActiveUnitPlayerID,
								newActiveUnitID,
								true,
								() => presentationLease
									.PublishInteractiveAndRelease(
										humanPlayerID,
										playerID == humanPlayerID
											? unitID
											: -1),
								presentationLease
									.ReacquireAndMarkUnknown,
								action => presentationLease
									.RunInteractiveWorldMapAnimation(
										humanPlayerID,
										playerID == humanPlayerID
											? unitID
											: -1,
										action),
								showModal => presentationLease
									.RunWorldMapModalOverlay(
										humanPlayerID,
										playerID == humanPlayerID
											? unitID
											: -1,
										showModal));
						unit.GoToDestination = OpenCivOneGame.InvalidPosition;
						this.parent.Var_70d8 = false;

						if (attackResult == -1)
							return;

						if (unit.UnitType == UnitTypeEnum.None)
						{
							unit.RemainingMoves = 0;
							return;
						}

						unit.RemainingMoves -= 3;

						if (unit.RemainingMoves < 0 || unit.RemainingMoves == 15)
						{
							unit.RemainingMoves = 0;
						}

						if (!newImprovements.HasFlag(TerrainImprovementFlagsEnum.City))
							return;

						int cityID = this.parent.Tools.F0_2dc4_00ba_GetCityByLocation(newX, newY);

						if (this.parent.GameData.Cities[cityID].PlayerID != this.parent.GameData.HumanPlayerID)
						{
							this.parent.GameData.Cities[cityID].StatusFlag |= 0x10;
						}

						if (unit.UnitType != UnitTypeEnum.None)
						{
							if (!this.parent.GameData.Cities[cityID].HasImprovement(ImprovementEnum.CityWalls))
							{
								if (currentTerrainType != TerrainTypeEnum.Water)
								{
									if (this.parent.GameData.DifficultyLevel != 0 || newActiveUnitPlayerID != this.parent.GameData.HumanPlayerID)
									{
										this.parent.GameData.Cities[cityID].ActualSize--;
									}
								}
							}
						}

						if (this.parent.GameData.Cities[cityID].ActualSize == 0)
						{
							// Instruction address 0x1403:0x2576, size: 5
							this.parent.Segment_1ade.F0_1ade_018e(cityID, newX, newY);
							this.parent.StartGameMenu.F5_0000_0e6c_TestIfAIPlayerIsDestroyed(newActiveUnitPlayerID, playerID);

							if (playerID == this.parent.GameData.HumanPlayerID)
							{
								newActiveUnitID = this.parent.MapManagement.F0_2aea_1458_GetCellActiveUnitID(newX, newY);
								newActiveUnitPlayerID = this.parent.MapManagement.F0_2aea_14e0_GetCellActiveUnitPlayerID(newX, newY);

								if (newActiveUnitID != -1)
								{
									this.parent.GameData.Players[newActiveUnitPlayerID].Units[newActiveUnitID].VisibleByPlayer |=
										(ushort)(1 << this.parent.GameData.HumanPlayerID);
								}
							}
						}

						if (playerID == this.parent.GameData.HumanPlayerID ||
							newActiveUnitPlayerID == this.parent.GameData.HumanPlayerID ||
							this.parent.Var_d806_DebugFlag)
						{
							this.parent.GameData.Cities[cityID].VisibleSize = this.parent.GameData.Cities[cityID].ActualSize;

							// Instruction address 0x1403:0x2606, size: 5
							DrawCellWithUnitWithPresentation(
								presentationLease,
								playerID,
								unitID,
								newX,
								newY);
						}

						if (this.parent.MapManagement.F0_2aea_14e0_GetCellActiveUnitPlayerID(newX, newY) == -1)
						{
							if (newActiveUnitPlayerID != this.parent.GameData.HumanPlayerID)
							{
								// Instruction address 0x1403:0x2641, size: 5
								this.parent.AIEngine.F0_25fb_3459_PlayerChangeCityProductionForSameContinent(newActiveUnitPlayerID, this.parent.MapManagement.F0_2aea_1942_GetGroupID(newX, newY));
							}
						}
						return;
					}

					// Move water unit only if destination is water or a city
					if (unit.UnitType != UnitTypeEnum.None && this.parent.GameData.Units[(int)unit.UnitType].MovementType == UnitMovementTypeEnum.Water &&
						newTerrainType != TerrainTypeEnum.Water && !newImprovements.HasFlag(TerrainImprovementFlagsEnum.City))
					{
						if (playerID ==
							this.parent.GameData.HumanPlayerID)
						{
							this.parent.Host.ShowTransientStatus(
								ClassicShellText.NavalUnitNeedsWater);
						}

						unit.GoToDestination = OpenCivOneGame.InvalidPosition;
						return;
					}

					if (unit.UnitType != UnitTypeEnum.None && this.parent.GameData.Units[(int)unit.UnitType].MovementType != UnitMovementTypeEnum.Land &&
						newImprovements.HasFlag(TerrainImprovementFlagsEnum.City) && this.parent.MapManagement.F0_2aea_1369_GetCityOwner(newX, newY) != playerID)
					{
						if (unit.UnitType != UnitTypeEnum.Nuclear)
						{
							// Instruction address 0x1403:0x2706, size: 5
							ShowWorldMapOverlayWithPresentation(
								presentationLease, playerID, unitID,
								() => this.parent.Help.F4_0000_03aa_ShowInstantWarningPopup("*OCCUPY"));

							unit.GoToDestination = OpenCivOneGame.InvalidPosition;
						}
						else
						{
							// Instruction address 0x1403:0x271f, size: 5
							this.parent.UnitManagement.F0_1866_0f10_DeleteUnit(playerID, unitID);
							// Instruction address 0x1403:0x2730, size: 5
							this.parent.Segment_29f3
								.F0_29f3_0d4d_NuclearAttackWithPresentation(
									playerID,
									newX,
									newY,
									action => presentationLease
										.RunInteractiveWorldMapAnimation(
											this.parent.GameData.HumanPlayerID,
											playerID == this.parent.GameData.HumanPlayerID
												? unitID
												: -1,
											action),
									showModal => presentationLease
										.RunWorldMapModalOverlay(
											this.parent.GameData.HumanPlayerID,
											playerID == this.parent.GameData.HumanPlayerID
												? unitID
												: -1,
											showModal));
						}
						return;
					}

					if (unit.RemainingMoves == 0)
					{
						return;
					}

					if (this.parent.GameData.Units[(int)unit.UnitType].MovementType == UnitMovementTypeEnum.Land)
					{
						if ((this.parent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(unit.Position.X, unit.Position.Y) & newImprovements).HasFlag(TerrainImprovementFlagsEnum.Road) &&
							unit.RemainingMoves != 0)
						{
							if (!this.parent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(unit.Position.X, unit.Position.Y).HasFlag(TerrainImprovementFlagsEnum.RailRoad) ||
								playerID != this.parent.GameData.HumanPlayerID || unit.GoToDestination.X != -1)
							{
								unit.RemainingMoves -= 1;
							}
						}
						else
						{
							if (unit.RemainingMoves != 3 &&
								this.parent.CAPI.RNG.Next(this.parent.GameData.Terrains[(int)newTerrainType].MovementCost * 3) > unit.RemainingMoves)
							{
								unit.RemainingMoves = 0;
								return;
							}

							unit.RemainingMoves -= (short)(this.parent.GameData.Terrains[(int)newTerrainType].MovementCost * 3);
						}
					}
					else
					{
						unit.RemainingMoves -= 3;
					}

					if (unit.RemainingMoves < 0)
					{
						unit.RemainingMoves = 0;
					}

					if (playerID != this.parent.GameData.HumanPlayerID)
					{
						if (unit.GoToNextDirection != -1)
						{
							if ((unit.GoToNextDirection ^ 0x4) == newMoveDirection)
							{
								if (this.parent.UnitManagement.F0_1866_1251_GetStackUnitValueSum(playerID, unitID, UnitStackValueTypeEnum.UnitCount) <= 2)
								{
									unit.GoToDestination = OpenCivOneGame.InvalidPosition;
									unit.GoToNextDirection = -1;
									unit.RemainingMoves = 0;

									return;
								}
							}
						}
						unit.GoToNextDirection = (short)newMoveDirection;
					}

					if (newActiveUnitID != -1 && playerID == newActiveUnitPlayerID &&
						playerID != this.parent.GameData.HumanPlayerID &&
						!newImprovements.HasFlag(TerrainImprovementFlagsEnum.City) &&
						!(UsesSmartEnhancements &&
							newTerrainType == TerrainTypeEnum.Water &&
							this.parent.GameData.Units[(int)unit.UnitType]
								.MovementType == UnitMovementTypeEnum.Land))
					{
						if (this.parent.GameData.Units[(int)unit.UnitType].MovementType == UnitMovementTypeEnum.Land ||
							(this.parent.GameData.Units[(int)unit.UnitType].MovementType == UnitMovementTypeEnum.Water &&
								unit.SpecialMoves != 0))
						{
							if (((unit.RemainingMoves != 0) ? 4 : 2) <= this.parent.UnitManagement.F0_1866_1251_GetStackUnitValueSum(playerID, newActiveUnitID, UnitStackValueTypeEnum.UnitCount))
								return;
						}
					}

					// Get playerID that owns this land
					int ownerPlayerID = this.parent.MapManagement.GetPlayerLandOwnership(newX, newY);

					if (ownerPlayerID != 0)
					{
						if (ownerPlayerID < 8)
						{
							if (newTerrainType != TerrainTypeEnum.Water && currentTerrainType != TerrainTypeEnum.Water &&
								(unit.UnitType != UnitTypeEnum.Diplomat && unit.UnitType != UnitTypeEnum.Caravan) &&
								(newImprovements.HasFlag(TerrainImprovementFlagsEnum.City) || newImprovements.HasFlag(TerrainImprovementFlagsEnum.Irrigation) ||
								newImprovements.HasFlag(TerrainImprovementFlagsEnum.Mines) || newImprovements.HasFlag(TerrainImprovementFlagsEnum.Road)) && ownerPlayerID != playerID)
							{
								if ((playerID == this.parent.GameData.HumanPlayerID || ownerPlayerID == this.parent.GameData.HumanPlayerID) &&
									this.parent.GameData.Units[(int)unit.UnitType].MovementType == UnitMovementTypeEnum.Land &&
									this.parent.MapManagement.F0_2aea_14e0_GetCellActiveUnitPlayerID(newX, newY) != playerID)
								{
									if (playerID == this.parent.GameData.HumanPlayerID)
									{
										unit.GoToDestination = OpenCivOneGame.InvalidPosition;

										if ((short)this.parent.Segment_29f3.F0_29f3_0c9e_ConfirmAttackAction(ownerPlayerID) != -1)
										{
											// Instruction address 0x1403:0x2a87, size: 5
											this.parent.Segment_2517.F0_2517_0aa1_ClearDiplomacyFlags(playerID, ownerPlayerID, DiplomacyFlagsEnum.Peace);
										}
										else
										{
											return;
										}
									}
									else if (ownerPlayerID == this.parent.GameData.HumanPlayerID &&
										this.parent.GameData.Players[ownerPlayerID].Diplomacy[playerID].HasFlag(DiplomacyFlagsEnum.Peace))
									{
										unit.RemainingMoves = 0;

										return;
									}
								}
							}

							if (playerID != ownerPlayerID)
							{
								if (((int)this.parent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(newX, newY) & 0xe) != 0)
								{
									unit.VisibleByPlayer |= (ushort)(1 << ownerPlayerID);
								}
							}
						}
					}

					int cityPlayerID1 = this.parent.MapManagement.F0_2aea_1369_GetCityOwner(newX, newY);

					if (playerID == 0 && newTerrainType != TerrainTypeEnum.Water &&
						(this.parent.GameData.MapVisibility[unit.Position.X, unit.Position.Y] & (0x1 << this.parent.GameData.HumanPlayerID)) != 0 &&
						(unit.VisibleByPlayer & (0x1 << this.parent.GameData.HumanPlayerID)) == 0 &&
						this.parent.GameData.Cities[this.parent.Tools.F0_2dc4_0102_FindNearestCity(unit.Position.X, unit.Position.Y)].PlayerID == this.parent.GameData.HumanPlayerID)
					{
						unit.VisibleByPlayer |= this.parent.GameData.MapVisibility[unit.Position.X, unit.Position.Y];
					}

					if (newImprovements.HasFlag(TerrainImprovementFlagsEnum.City) && cityPlayerID1 != playerID &&
						(this.parent.GameData.MapVisibility[newX, newY] & (0x1 << this.parent.GameData.HumanPlayerID)) != 0 &&
						(this.parent.GameData.Players[this.parent.GameData.HumanPlayerID].Diplomacy[playerID].HasFlag(DiplomacyFlagsEnum.Unknown40) ||
							this.parent.GameData.Players[this.parent.GameData.HumanPlayerID].Diplomacy[cityPlayerID1].HasFlag(DiplomacyFlagsEnum.Unknown40)))
					{
						unit.VisibleByPlayer |= (ushort)(1 << this.parent.GameData.HumanPlayerID);
					}

					if (newTerrainType == TerrainTypeEnum.Water)
					{
						if (((int)this.parent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(newX, newY) & 0x2) != 0)
						{
							unit.VisibleByPlayer |= (ushort)(1 << cityPlayerID1);
						}
					}

					GPoint originPosition = unit.Position;
					int[] embarkedLandCargoUnitIDs =
						GetEmbarkedLandCargoUnitIDs(
							playerID,
							unitID,
							originPosition);
					int[] embarkedCarrierAircraftUnitIDs =
						GetEmbarkedCarrierAircraftUnitIDs(
							playerID,
							unitID,
							originPosition);

					ushort humanMoveVisibilityMask =
						(ushort)(0x1 << this.parent.GameData.HumanPlayerID);
					bool movingHumanUnit =
						playerID == this.parent.GameData.HumanPlayerID;
					bool debugShowsAiMove =
						this.parent.Var_d806_DebugFlag && playerID != 0;
					bool movingUnitVisibleToHuman =
						(unit.VisibleByPlayer & humanMoveVisibilityMask) != 0;
					bool originCellKnownToHuman =
						(this.parent.GameData.MapVisibility[unit.Position.X, unit.Position.Y] &
							humanMoveVisibilityMask) != 0;
					bool destinationCellKnownToHuman =
						(this.parent.GameData.MapVisibility[newX, newY] &
							humanMoveVisibilityMask) != 0;

					if (!this.parent.GameData.GameSettingFlags.EnemyMoves && !movingHumanUnit)
					{
						if (debugShowsAiMove ||
							(movingUnitVisibleToHuman && originCellKnownToHuman))
						{
							// Instruction address 0x1403:0x2cd5, size: 5
							DrawCellWithPresentation(
								presentationLease,
								playerID,
								unitID,
								unit.Position.X,
								unit.Position.Y);
						}
					}
					else if (movingHumanUnit ||
						debugShowsAiMove ||
						(movingUnitVisibleToHuman &&
							originCellKnownToHuman &&
							destinationCellKnownToHuman))
					{
						// Instruction address 0x1403:0x2cb3, size: 5
						CenterMapWithPresentation(
							presentationLease,
							playerID,
							unitID,
							newX,
							newY);
						// Instruction address 0x1403:0x2cc4, size: 5
						AnimateUnitMoveWithPresentation(
							presentationLease,
							playerID,
							unitID,
							newMoveDirection);
					}

					// Instruction address 0x1403:0x2d01, size: 5
					this.parent.MapManagement.F0_2aea_1412_SetCellActivePlayerID(unit.Position.X, unit.Position.Y, playerID, unitID);

					// Instruction address 0x1403:0x2d21, size: 5
					this.parent.MapManagement.F0_2aea_13cb_SetCellPlayerID(newX, newY, playerID, unitID);

					unit.Position = new(newX, newY);
					unit.VisibleByPlayer = 0;
					MoveEmbarkedLandCargo(
						playerID,
						unitID,
						embarkedLandCargoUnitIDs,
						originPosition,
						unit.Position);
					MoveEmbarkedCarrierAircraft(
						playerID,
						unitID,
						embarkedCarrierAircraftUnitIDs,
						originPosition,
						unit.Position);

					if (playerID != this.parent.GameData.HumanPlayerID &&
						this.parent.GameData.Units[(int)unit.UnitType]
							.MovementType != UnitMovementTypeEnum.Water &&
						(!UsesSmartEnhancements ||
							newTerrainType != TerrainTypeEnum.Water))
					{
						unit.ClearStatusFlags(UnitStatusEnum.Sentry | UnitStatusEnum.SettlerBuildRoadOrRail | UnitStatusEnum.Fortifying |
							 UnitStatusEnum.Fortified | UnitStatusEnum.SettlerBuildIrrigation | UnitStatusEnum.SettlerBuildMineOrForest);
					}

					if (ownerPlayerID != 0 && ownerPlayerID < 8 && ownerPlayerID != playerID)
					{
						// Instruction address 0x1403:0x2d9d, size: 5
						this.parent.MapManagement.SetPlayerLandOwnership(newX, newY, 0);
					}

					if (unit.GoToDestination.X == newX && unit.GoToDestination.Y == newY)
					{
						unit.GoToDestination = OpenCivOneGame.InvalidPosition;
						unit.GoToNextDirection = -1;

						if (playerID != this.parent.GameData.HumanPlayerID)
						{
							unit.RemainingMoves = 0;
						}
					}

					if (currentTerrainType == TerrainTypeEnum.Water && newTerrainType != TerrainTypeEnum.Water &&
						this.parent.GameData.Units[(int)unit.UnitType].MovementType != UnitMovementTypeEnum.Water)
					{
						unit.RemainingMoves = 0;
					}

					int destinationCityID = -1;
					if (newImprovements.HasFlag(TerrainImprovementFlagsEnum.City))
					{
						destinationCityID =
							this.parent.Tools.F0_2dc4_00ba_GetCityByLocation(
								newX,
								newY);

						if (destinationCityID < 0)
						{
							// A destroyed city must not leave an orphaned map
							// marker behind. Older saves and interrupted capture
							// paths can contain this mismatch; repair it at the
							// movement boundary before takeover logic sees -1.
							this.parent.MapManagement
								.F0_2aea_16ee_ClearTerrainImprovements(
									newX,
									newY,
									TerrainImprovementFlagsEnum.City);
							this.parent.MapManagement
								.F0_2aea_1601_UpdateVisibleCellStatus(
									newX,
									newY);
						}
					}

					if (destinationCityID >= 0 && cityPlayerID1 != playerID)
					{
						unit.VisibleByPlayer |= (ushort)(1 << cityPlayerID1);

						// Instruction address 0x1403:0x303e, size: 5
						this.parent.Segment_2459.F0_2459_0000_CityTakeover(
							playerID,
							destinationCityID,
							false);
						// Instruction address 0x1403:0x304c, size: 5
						this.parent.MapManagement.F0_2aea_1511_ActiveUnitSetFlag8(newX, newY);
					}

					// Instruction address 0x1403:0x305d, size: 5
					this.parent.MapManagement.F0_2aea_138c_SetCityOwner(newX, newY, playerID);
					// Instruction address 0x1403:0x3079, size: 5
					this.parent.UnitManagement.F0_1866_01dc(newX, newY, playerID, unitID, true);

					if (this.parent.MapManagement.F0_2aea_1894_CellHasMinorTribeHut(newX, newY, newTerrainType))
					{
						// Instruction address 0x1403:0x30a0, size: 5
						this.parent.UnitManagement.F0_1866_1931_FoundMinorTribeHut(playerID, unitID);

						this.parent.GameData.MapVisibility[newX, newY] |= 1;
					}

					if (newTerrainType == TerrainTypeEnum.Water &&
						this.parent.GameData.Units[(int)unit.UnitType].MovementType != UnitMovementTypeEnum.Air &&
						this.parent.GameData.Units[(int)unit.UnitType].MovementType != UnitMovementTypeEnum.Water)
					{
						// Instruction address 0x1403:0x30f6, size: 5
						this.parent.UnitManagement.F0_1866_1560_UnitStack(playerID, unitID);
					}

					if (playerID == 0 && newTerrainType != TerrainTypeEnum.Water)
					{
						if ((this.parent.GameData.MapVisibility[newX, newY] & (0x1 << this.parent.GameData.HumanPlayerID)) != 0 &&
							(unit.VisibleByPlayer & (0x1 << this.parent.GameData.HumanPlayerID)) == 0 &&
							this.parent.GameData.Cities[this.parent.Tools.F0_2dc4_0102_FindNearestCity(newX, newY)].PlayerID == this.parent.GameData.HumanPlayerID)
						{
							unit.VisibleByPlayer |= this.parent.GameData.MapVisibility[newX, newY];
						}
					}

					bool movedUnitVisibleToHuman =
						(unit.VisibleByPlayer & humanMoveVisibilityMask) != 0;
					bool movedUnitCellKnownToHuman =
						(this.parent.GameData.MapVisibility[newX, newY] &
							humanMoveVisibilityMask) != 0;

					if (movingHumanUnit ||
						debugShowsAiMove ||
						(movedUnitVisibleToHuman && movedUnitCellKnownToHuman))
					{
						DrawSettledUnitWithPresentation(
							presentationLease,
							playerID,
							unitID,
							newX,
							newY);
					}

					unitMoveCount = 0;

					if (newImprovements.HasFlag(TerrainImprovementFlagsEnum.City) && this.parent.GameData.Units[(int)unit.UnitType].TurnsOutside != 0)
					{
						unit.ClearStatusFlags(UnitStatusEnum.SettlerBuildRoadOrRail);
						unit.RemainingMoves = 0;
						unit.GoToDestination = OpenCivOneGame.InvalidPosition;
					}

					if (this.parent.GameData.Units[(int)unit.UnitType].TurnsOutside != 0)
					{
						if (this.parent.GameData.Units[(int)unit.UnitType].MovementType == UnitMovementTypeEnum.Water)
						{
							if (this.parent.UnitManagement.F0_1866_1331_CountUnitTypesInStack(playerID, unitID, UnitTypeEnum.Carrier) != 0)
							{
								unit.ClearStatusFlags(UnitStatusEnum.SettlerBuildRoadOrRail);
								unit.RemainingMoves = 0;
								unit.SpecialMoves = this.parent.GameData.Units[(int)unit.UnitType].TurnsOutside;
							}
						}
					}
				}
			}
		}

		private void AnimateUnitMoveWithPresentation(
			OpenCivOne.Presentation.ClassicRuntimePresentationState
				.ClassicRuntimeMutationLease presentationLease,
			int movingPlayerID,
			int movingUnitID,
			int moveDirection)
		{
			int humanPlayerID = this.parent.GameData.HumanPlayerID;
			presentationLease.RunInteractiveWorldMapAnimation(
				humanPlayerID,
				movingPlayerID == humanPlayerID ? movingUnitID : -1,
				() => this.parent.UnitManagement
					.F0_1866_1d55_AnimateUnitMove(
						movingPlayerID,
						movingUnitID,
						moveDirection));
		}

		private void DrawVisibleMapWithPresentation(
			OpenCivOne.Presentation.ClassicRuntimePresentationState
				.ClassicRuntimeMutationLease presentationLease,
			int playerID,
			int activeUnitID,
			int viewX,
			int viewY)
		{
			presentationLease.RunInteractiveWorldMapAnimation(
				this.parent.GameData.HumanPlayerID,
				playerID == this.parent.GameData.HumanPlayerID &&
					activeUnitID is >= 0 and < 128
						? activeUnitID
						: -1,
				() => this.parent.MapManagement
					.F0_2aea_0008_DrawVisibleMap(
						playerID,
						viewX,
						viewY));
		}

		private void DrawSettledUnitWithPresentation(
			OpenCivOne.Presentation.ClassicRuntimePresentationState
				.ClassicRuntimeMutationLease presentationLease,
			int playerID,
			int unitID,
			int mapX,
			int mapY)
		{
			int humanPlayerID = this.parent.GameData.HumanPlayerID;
			presentationLease.RunInteractiveWorldMapAnimation(
				humanPlayerID,
				playerID == humanPlayerID ? unitID : -1,
				() =>
				{
					if (playerID == humanPlayerID ||
						this.parent.GameData.GameSettingFlags.EnemyMoves)
					{
						this.parent.UnitManagement.F0_1866_16a9_CenterMap(
							humanPlayerID,
							mapX,
							mapY);
						this.parent.MapManagement.F0_2aea_0e29_DrawUnit(
							playerID,
							unitID);
						if (playerID != humanPlayerID)
						{
							this.parent.CommonTools.WaitTimer(30);
						}
					}
					else if (this.parent.MapManagement
						.F0_2aea_0e29_DrawUnit(playerID, unitID))
					{
						this.parent.CommonTools.WaitTimer(10);
					}
				});
		}

		private void DrawCellWithUnitWithPresentation(
			OpenCivOne.Presentation.ClassicRuntimePresentationState
				.ClassicRuntimeMutationLease presentationLease,
			int playerID,
			int activeUnitID,
			int mapX,
			int mapY) =>
			presentationLease.RunInteractiveWorldMapAnimation(
				this.parent.GameData.HumanPlayerID,
				playerID == this.parent.GameData.HumanPlayerID &&
					activeUnitID is >= 0 and < 128
						? activeUnitID
						: -1,
				() => this.parent.MapManagement
					.F0_2aea_11d4_DrawCellWithUnit(mapX, mapY));

		private void DrawCellWithPresentation(
			OpenCivOne.Presentation.ClassicRuntimePresentationState
				.ClassicRuntimeMutationLease presentationLease,
			int playerID,
			int activeUnitID,
			int mapX,
			int mapY) =>
			presentationLease.RunInteractiveWorldMapAnimation(
				this.parent.GameData.HumanPlayerID,
				playerID == this.parent.GameData.HumanPlayerID &&
					activeUnitID is >= 0 and < 128
						? activeUnitID
						: -1,
				() => this.parent.MapManagement
					.F0_2aea_03ba_DrawCell(mapX, mapY));

		private void CenterMapWithPresentation(
			OpenCivOne.Presentation.ClassicRuntimePresentationState
				.ClassicRuntimeMutationLease presentationLease,
			int playerID,
			int activeUnitID,
			int mapX,
			int mapY)
		{
			presentationLease.RunInteractiveWorldMapAnimation(
				this.parent.GameData.HumanPlayerID,
				playerID == this.parent.GameData.HumanPlayerID
					? activeUnitID
					: -1,
				() => this.parent.UnitManagement.F0_1866_16a9_CenterMap(
					this.parent.GameData.HumanPlayerID,
					mapX,
					mapY));
		}

		private int ShowWorldMapDialogWithPresentation(
			OpenCivOne.Presentation.ClassicRuntimePresentationState
				.ClassicRuntimeMutationLease presentationLease,
			int playerID,
			int activeUnitID,
			string text,
			int x,
			int y) =>
			presentationLease.RunWorldMapModalOverlay(
				this.parent.GameData.HumanPlayerID,
				playerID == this.parent.GameData.HumanPlayerID
					? activeUnitID
					: -1,
				() => this.parent.Segment_1238.F0_1238_001e_ShowDialog(
					text,
					x,
					y));

		private void ShowWorldMapOverlayWithPresentation(
			OpenCivOne.Presentation.ClassicRuntimePresentationState
				.ClassicRuntimeMutationLease presentationLease,
			int playerID,
			int activeUnitID,
			Action showOverlay) =>
			presentationLease.RunWorldMapModalOverlay(
				this.parent.GameData.HumanPlayerID,
				playerID == this.parent.GameData.HumanPlayerID &&
					activeUnitID is >= 0 and < 128
						? activeUnitID
						: -1,
				showOverlay);

		private bool IsMovementBlockedByZoneOfControl(
			int playerID,
			Unit unit,
			TerrainTypeEnum sourceTerrain,
			int destinationActiveUnitID,
			int destinationX,
			int destinationY)
		{
			UnitMovementTypeEnum movementType =
				this.parent.GameData.Units[
					(int)unit.UnitType].MovementType;
			bool destinationOccupied =
				destinationActiveUnitID != -1;
			if (!ClassicZoneOfControlPolicy.Applies(
					movementType,
					unit.UnitType,
					sourceTerrain,
					destinationOccupied))
			{
				return false;
			}

			bool sourceInEnemyControl =
				UsesSmartEnhancements
					? this.parent.UnitManagement
						.IsKnownEnemyZoneOfControlAt(
							playerID,
							unit.Position)
					: this.parent.UnitManagement
						.F0_1866_1725_IsUnitNear(
							playerID,
							unit.Position.X,
							unit.Position.Y);
			bool destinationInEnemyControl =
				sourceInEnemyControl &&
				(UsesSmartEnhancements
					? this.parent.UnitManagement
						.IsKnownEnemyZoneOfControlAt(
							playerID,
							new GPoint(destinationX, destinationY))
					: this.parent.UnitManagement
						.F0_1866_1725_IsUnitNear(
							playerID,
							destinationX,
							destinationY));
			return ClassicZoneOfControlPolicy.Blocks(
				movementType,
				unit.UnitType,
				sourceTerrain,
				destinationOccupied,
				sourceInEnemyControl,
				destinationInEnemyControl);
		}

		private int[] GetEmbarkedLandCargoUnitIDs(
			int playerID,
			int transportUnitID,
			GPoint originPosition)
		{
			if (UsesSmartEnhancements)
			{
				return this.parent.UnitManagement
					.GetAssignedEmbarkedLandCargoUnitIDs(
						playerID,
						transportUnitID,
						originPosition);
			}

			Player player = this.parent.GameData.Players[playerID];
			Unit transport = player.Units[transportUnitID];
			UnitDefinition transportDefinition =
				this.parent.GameData.Units[(int)transport.UnitType];

			if (transportDefinition.UnitRoleType !=
					UnitRoleTypeEnum.SeaTransport ||
				transportDefinition.TransportCapacity <= 0 ||
				transport.NextUnitID == -1 ||
				this.parent.MapManagement.GetTerrainType(
					originPosition.X,
					originPosition.Y) != TerrainTypeEnum.Water)
			{
				return [];
			}

			var cargoUnitIDs = new List<int>(
				transportDefinition.TransportCapacity);
			var visitedUnitIDs = new HashSet<int>
			{
				transportUnitID
			};
			int currentUnitID = transport.NextUnitID;

			while (currentUnitID != -1 &&
				currentUnitID != transportUnitID &&
				currentUnitID < player.Units.Length &&
				currentUnitID >= 0 &&
				visitedUnitIDs.Add(currentUnitID))
			{
				Unit candidate = player.Units[currentUnitID];
				int nextUnitID = candidate.NextUnitID;

				if (candidate.UnitType != UnitTypeEnum.None &&
					candidate.Position == originPosition &&
					this.parent.GameData.Units[(int)candidate.UnitType]
						.MovementType == UnitMovementTypeEnum.Land)
				{
					cargoUnitIDs.Add(currentUnitID);
					if (cargoUnitIDs.Count >=
						transportDefinition.TransportCapacity)
					{
						break;
					}
				}

				currentUnitID = nextUnitID;
			}

			return [.. cargoUnitIDs];
		}

		private void MoveEmbarkedLandCargo(
			int playerID,
			int transportUnitID,
			IReadOnlyList<int> cargoUnitIDs,
			GPoint originPosition,
			GPoint destinationPosition)
		{
			Player player = this.parent.GameData.Players[playerID];

			foreach (int cargoUnitID in cargoUnitIDs)
			{
				if (cargoUnitID < 0 ||
					cargoUnitID >= player.Units.Length)
				{
					continue;
				}

				Unit cargo = player.Units[cargoUnitID];
				if (cargo.UnitType == UnitTypeEnum.None ||
					cargo.Position != originPosition ||
					this.parent.GameData.Units[(int)cargo.UnitType]
						.MovementType != UnitMovementTypeEnum.Land)
				{
					continue;
				}

				this.parent.MapManagement
					.F0_2aea_1412_SetCellActivePlayerID(
						originPosition.X,
						originPosition.Y,
						playerID,
						cargoUnitID);
				this.parent.Segment_29f3.F0_29f3_0b66_AddUnitToStack(
					playerID,
					cargoUnitID,
					transportUnitID);

				cargo.Position = destinationPosition;
				cargo.VisibleByPlayer = 0;
				cargo.GoToNextDirection = -1;
			}
		}

		private int[] GetEmbarkedCarrierAircraftUnitIDs(
			int playerID,
			int carrierUnitID,
			GPoint originPosition)
		{
			Player player = this.parent.GameData.Players[playerID];
			Unit carrier = player.Units[carrierUnitID];

			if (carrier.UnitType != UnitTypeEnum.Carrier ||
				carrier.NextUnitID == -1 ||
				this.parent.MapManagement.GetTerrainType(
					originPosition.X,
					originPosition.Y) != TerrainTypeEnum.Water)
			{
				return [];
			}

			var aircraftUnitIDs = new List<int>();
			var visitedUnitIDs = new HashSet<int>
			{
				carrierUnitID
			};
			int currentUnitID = carrier.NextUnitID;
			int inspectedUnitCount = 0;

			while (currentUnitID != -1 &&
				currentUnitID != carrierUnitID &&
				currentUnitID < player.Units.Length &&
				currentUnitID >= 0 &&
				visitedUnitIDs.Add(currentUnitID) &&
				inspectedUnitCount < 20 &&
				aircraftUnitIDs.Count < CarrierAircraftCapacity)
			{
				inspectedUnitCount++;
				Unit candidate = player.Units[currentUnitID];
				int nextUnitID = candidate.NextUnitID;
				bool humanAircraft =
					playerID == this.parent.GameData.HumanPlayerID &&
					!candidate.Status.HasFlag(UnitStatusEnum.Sentry);
				bool aiAircraft =
					playerID != this.parent.GameData.HumanPlayerID &&
					(candidate.Status &
						(UnitStatusEnum.Fortifying |
							UnitStatusEnum.Fortified)) ==
						UnitStatusEnum.None &&
					candidate.NextUnitID != -1;

				if (candidate.UnitType != UnitTypeEnum.None &&
					candidate.Position == originPosition &&
					this.parent.GameData.Units[(int)candidate.UnitType]
						.MovementType == UnitMovementTypeEnum.Air &&
					(humanAircraft || aiAircraft))
				{
					aircraftUnitIDs.Add(currentUnitID);
				}

				currentUnitID = nextUnitID;
			}

			return [.. aircraftUnitIDs];
		}

		private void MoveEmbarkedCarrierAircraft(
			int playerID,
			int carrierUnitID,
			IReadOnlyList<int> aircraftUnitIDs,
			GPoint originPosition,
			GPoint destinationPosition)
		{
			Player player = this.parent.GameData.Players[playerID];
			if (carrierUnitID < 0 ||
				carrierUnitID >= player.Units.Length ||
				player.Units[carrierUnitID].UnitType != UnitTypeEnum.Carrier ||
				player.Units[carrierUnitID].Position != destinationPosition)
			{
				return;
			}

			foreach (int aircraftUnitID in aircraftUnitIDs)
			{
				if (aircraftUnitID < 0 ||
					aircraftUnitID >= player.Units.Length)
				{
					continue;
				}

				Unit aircraft = player.Units[aircraftUnitID];
				if (aircraft.UnitType == UnitTypeEnum.None ||
					aircraft.Position != originPosition ||
					this.parent.GameData.Units[(int)aircraft.UnitType]
						.MovementType != UnitMovementTypeEnum.Air)
				{
					continue;
				}

				this.parent.MapManagement
					.F0_2aea_1412_SetCellActivePlayerID(
						originPosition.X,
						originPosition.Y,
						playerID,
						aircraftUnitID);
				this.parent.MapManagement
					.F0_2aea_13cb_SetCellPlayerID(
						destinationPosition.X,
						destinationPosition.Y,
						playerID,
						aircraftUnitID);

				aircraft.Position = destinationPosition;
				aircraft.VisibleByPlayer = 0;
				aircraft.GoToNextDirection = -1;

				UnitDefinition aircraftDefinition =
					this.parent.GameData.Units[(int)aircraft.UnitType];
				if (aircraftDefinition.TurnsOutside != 0)
				{
					aircraft.SpecialMoves =
						(short)(aircraftDefinition.TurnsOutside - 1);
				}
			}
		}

		/// <summary>
		/// ?
		/// </summary>
		/// <param name="x"></param>
		/// <param name="y"></param>
		public void F0_1403_3ed7(int x, int y)
		{
			//this.oCPU.Log.EnterBlock("'Fn2'(Cdecl, Far, Return) at 0x3ed7");

			// function body
			if ((this.parent.GameData.MapVisibility[x, y] & (1 << this.parent.GameData.HumanPlayerID)) != 0 || this.parent.Var_d806_DebugFlag)
			{
				// Instruction address 0x1403:0x3f09, size: 5
				this.parent.MapManagement.F0_2aea_11d4_DrawCellWithUnit(x, y);
			}
		}

		/// <summary>
		/// ?
		/// </summary>
		/// <param name="playerID"></param>
		/// <param name="unitID"></param>
		private void F0_1403_3f13_RedrawUnit(int playerID, int unitID)
		{
			//this.oCPU.Log.EnterBlock("'Fn3'(Cdecl, Far, Return) at 0x3f13");

			// function body
			if (playerID == this.parent.GameData.HumanPlayerID ||
				(this.parent.GameData.Players[playerID].Units[unitID].VisibleByPlayer & (0x1 << this.parent.GameData.HumanPlayerID)) != 0)
			{
				// Instruction address 0x1403:0x3f5d, size: 5
				this.parent.MapManagement.F0_2aea_11d4_DrawCellWithUnit(
					this.parent.GameData.Players[playerID].Units[unitID].Position.X,
					this.parent.GameData.Players[playerID].Units[unitID].Position.Y);
			}
		}

		/// <summary>
		/// Get preferred improvement for this cell
		/// </summary>
		/// <param name="x"></param>
		/// <param name="y"></param>
		/// <returns></returns>
		public TerrainImprovementFlagsEnum F0_1403_3f68_GetPreferredImprovement(int x, int y)
		{
			//this.oCPU.Log.EnterBlock("'Fn4'(Cdecl, Far, Return) at 0x3f68");
			// function body
			if ((this.parent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(x, y) & 
				(TerrainImprovementFlagsEnum.City | TerrainImprovementFlagsEnum.Irrigation | TerrainImprovementFlagsEnum.Mines)) == TerrainImprovementFlagsEnum.None)
			{
				// Instruction address 0x1403:0x3f8a, size: 5
				TerrainTypeEnum terrainType = this.parent.MapManagement.GetTerrainType(x, y);

				if (this.parent.GameData.TerrainModifications[(int)terrainType].MiningEffect > -3)
				{
					if (this.parent.GameData.TerrainModifications[(int)terrainType].IrrigationEffect == -2 && this.parent.MapManagement.CanIrrigateCell(x, y))
					{
						// Irrigation
						return TerrainImprovementFlagsEnum.Irrigation;
					}
				}
				else
				{
					// Mine
					return TerrainImprovementFlagsEnum.Mines;
				}
			}

			// None
			return TerrainImprovementFlagsEnum.None;
		}

		/// <summary>
		/// ?
		/// </summary>
		/// <param name="playerID"></param>
		/// <param name="unitID"></param>
		public void F0_1403_4060(int playerID, int unitID)
		{
			//this.oCPU.Log.EnterBlock("'Fn6'(Cdecl, Far, Return) at 0x4060");

			// Local variables
			int Local_2;
			int Local_4;
			int Local_6;
			int Local_8;
			int Local_a;
			int Local_10;
			int Local_12;

			// function body
			// Instruction address 0x1403:0x407c, size: 5
			this.parent.Segment_1238.F0_1238_1bb2_FillRectangleWithShadow(0, 97, 80, 103);

			if (unitID == 128)
			{
				// Instruction address 0x1403:0x409a, size: 5
				this.parent.DrawTools.F0_1182_005c_DrawStringToScreen0(
					ClassicGameText.Current[ClassicGameTextKey.EndOfTurn],
					4, 124, 0);
				// Instruction address 0x1403:0x40b1, size: 5
				this.parent.DrawTools.F0_1182_005c_DrawStringToScreen0(
					ClassicGameText.Current[ClassicGameTextKey.PressEnter],
					4, 136, 0);
				// Instruction address 0x1403:0x44f5, size: 5
				this.parent.DrawTools.F0_1182_005c_DrawStringToScreen0(
					ClassicGameText.Current[ClassicGameTextKey.ToContinue],
					4, 144, 0);
			}
			else
			{
				if (this.parent.GameData.Players[playerID].Units[unitID].UnitType != UnitTypeEnum.None)
				{
					Local_a = 99;

					// Instruction address 0x1403:0x40f3, size: 5
					Player player = this.parent.GameData.Players[playerID];
					string nationality = player.Nationality;
					if (player.NationalityID >= 0 &&
						player.NationalityID <
							this.parent.GameData.Nations.Length)
					{
						nationality = ClassicDisplayNames.Nation(
							player.NationalityID,
							player.Nationality,
							this.parent.GameData.Nations[
								player.NationalityID].Nationality);
					}
					this.parent.DrawTools.F0_1182_005c_DrawStringToScreen0(
						nationality, 4, 99, 0);

					Local_a += 8;

					// Instruction address 0x1403:0x4133, size: 5
					UnitTypeEnum unitType =
						this.parent.GameData.Players[playerID].Units[
							unitID].UnitType;
					this.parent.DrawTools.F0_1182_005c_DrawStringToScreen0(
						ClassicDisplayNames.Unit(
							unitType,
							this.parent.GameData.Units[(int)unitType].Name),
						4, Local_a, 0);

					Local_a += 8;

					if ((this.parent.GameData.Players[playerID].Units[unitID].Status & UnitStatusEnum.Veteran) != UnitStatusEnum.None)
					{
						// Instruction address 0x1403:0x4154, size: 5
						this.parent.DrawTools.F0_1182_005c_DrawStringToScreen0(
							ClassicGameText.Current[
								ClassicGameTextKey.Veteran],
							8, Local_a, 0);

						Local_a += 8;
					}

					int Local_e = this.parent.Tools.F0_2dc4_007c_CheckValueRange(this.parent.GameData.Players[playerID].Units[unitID].RemainingMoves / 3, 0, 99);
					int Local_e1 = Local_e + ((this.parent.GameData.Units[(int)this.parent.GameData.Players[playerID].Units[unitID].UnitType].TurnsOutside != 0) ?
					(this.parent.GameData.Units[(int)this.parent.GameData.Players[playerID].Units[unitID].UnitType].MoveCount *
							this.parent.GameData.Players[playerID].Units[unitID].SpecialMoves) : 0);
					int Local_c = this.parent.GameData.Players[playerID].Units[unitID].RemainingMoves % 3;

					// Instruction address 0x1403:0x4285, size: 5
					this.parent.DrawTools.F0_1182_005c_DrawStringToScreen0(
						ClassicGameText.Current.Format(
							ClassicGameTextKey.UnitMoves,
							Local_e,
							(Local_c != 0) ? $".{Local_c}" : "",
							(Local_e != Local_e1) ? $"({Local_e1})" : ""),
						4, Local_a, 0);

					Local_a += 8;

					// Instruction address 0x1403:0x42c2, size: 5
					this.parent.DrawTools.F0_1182_005c_DrawStringToScreen0(this.parent.Segment_2459.F0_2459_08c6_GetCityName(this.parent.GameData.Players[playerID].Units[unitID].HomeCityID), 4, Local_a, 0);

					Local_a += 8;

					// Instruction address 0x1403:0x4325, size: 5
					TerrainTypeEnum terrainType =
						this.parent.MapManagement.GetTerrainType(
							this.parent.GameData.Players[playerID].Units[
								unitID].Position.X,
							this.parent.GameData.Players[playerID].Units[
								unitID].Position.Y);
					this.parent.DrawTools.F0_1182_005c_DrawStringToScreen0(
						$"({ClassicDisplayNames.Terrain(
							terrainType,
							this.parent.GameData.Terrains[
								(int)terrainType].Name)})",
						4, Local_a, 0);

					Local_a += 8;

					Local_10 = (int)this.parent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(
						this.parent.GameData.Players[playerID].Units[unitID].Position.X, this.parent.GameData.Players[playerID].Units[unitID].Position.Y);

					if ((Local_10 & 0x10) != 0)
					{
						// Instruction address 0x1403:0x4371, size: 5
						this.parent.DrawTools.F0_1182_005c_DrawStringToScreen0(
							ClassicGameText.Current[
								ClassicGameTextKey.RailRoadLabel],
							4, Local_a, 0);

						Local_a += 8;
					}
					else
					{
						if ((Local_10 & 0x8) != 0)
						{
							// Instruction address 0x1403:0x4371, size: 5
							this.parent.DrawTools.F0_1182_005c_DrawStringToScreen0(
								ClassicGameText.Current[
									ClassicGameTextKey.RoadLabel],
								4, Local_a, 0);

							Local_a += 8;
						}
					}

					if ((Local_10 & 0x2) != 0)
					{
						// Instruction address 0x1403:0x43a6, size: 5
						this.parent.DrawTools.F0_1182_005c_DrawStringToScreen0(
							ClassicGameText.Current[
								ClassicGameTextKey.IrrigationLabel],
							4, Local_a, 0);

						Local_a += 8;
					}
					else
					{
						if ((Local_10 & 0x4) != 0)
						{
							// Instruction address 0x1403:0x43a6, size: 5
							this.parent.DrawTools.F0_1182_005c_DrawStringToScreen0(
								ClassicGameText.Current[
									ClassicGameTextKey.MiningLabel],
								4, Local_a, 0);

							Local_a += 8;
						}
					}

					if ((Local_10 & 0x40) != 0)
					{
						// Instruction address 0x1403:0x43c6, size: 5
						this.parent.DrawTools.F0_1182_005c_DrawStringToScreen0(
							ClassicGameText.Current[
								ClassicGameTextKey.PollutionLabel],
							4, Local_a, 0);

						Local_a += 8;
					}

					Local_a += 4;
					Local_4 = this.parent.GameData.Players[playerID].Units[unitID].NextUnitID;
					Local_8 = 8;

					if (((int)this.parent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(
						this.parent.GameData.Players[playerID].Units[unitID].Position.X,
						this.parent.GameData.Players[playerID].Units[unitID].Position.Y) & 0x1) != 0)
					{
						Local_2 = this.parent.Tools.F0_2dc4_00ba_GetCityByLocation(
							this.parent.GameData.Players[playerID].Units[unitID].Position.X,
							this.parent.GameData.Players[playerID].Units[unitID].Position.Y);

						for (Local_6 = 0; Local_6 < 2; Local_6++)
						{
							Local_12 = this.parent.GameData.Cities[Local_2].Unknown[Local_6];

							if (Local_12 != -1)
							{
								this.parent.GameData.Players[playerID].Units[127].UnitType = (UnitTypeEnum)(Local_12 & 0x3f);
								this.parent.GameData.Players[playerID].Units[127].Status = UnitStatusEnum.Fortified;
								this.parent.GameData.Players[playerID].Units[127].GoToDestination = OpenCivOneGame.InvalidPosition;

								// Instruction address 0x1403:0x4468, size: 5
								this.parent.MapManagement.F0_2aea_0fb3_DrawUnitWithStatus(playerID, 127, Local_8, Local_a);

								this.parent.GameData.Players[playerID].Units[127].UnitType = UnitTypeEnum.None;

								Local_8 += 16;
							}
						}
					}

					while (Local_4 != -1)
					{
						if (Local_4 == unitID || Local_a >= 184)
							break;

						// Instruction address 0x1403:0x449f, size: 5
						this.parent.MapManagement.F0_2aea_0fb3_DrawUnitWithStatus(playerID, Local_4, Local_8, Local_a);

						Local_8 += 16;

						if (Local_8 > 64)
						{
							Local_8 = 8;
							Local_a += 16;
						}

						Local_4 = this.parent.GameData.Players[playerID].Units[Local_4].NextUnitID;
					}

					if (Local_4 != -1 && Local_4 != unitID)
					{
						// Instruction address 0x1403:0x44f5, size: 5
						this.parent.DrawTools.F0_1182_005c_DrawStringToScreen0("+", 74, 192, 0);
					}
				}
			}
		}

		/// <summary>
		/// Test is new map coordinates are valid
		/// </summary>
		/// <param name="x"></param>
		/// <param name="y"></param>
		/// <returns></returns>
		public bool F0_1403_4508_ValidateMapCoordinates(int x, int y)
		{
			//this.oCPU.Log.EnterBlock("'Fn7'(Cdecl, Far, Return) at 0x4508");
			// function body
			if (x < 16 && this.parent.Var_d4cc_MapViewX >= 65)
			{
				x += 80;
			}

			return (x >= this.parent.Var_d4cc_MapViewX && x < this.parent.Var_d4cc_MapViewX + 15 &&
				y >= this.parent.Var_d75e_MapViewY && y < this.parent.Var_d75e_MapViewY + 12);
		}

		/// <summary>
		/// ?
		/// </summary>
		/// <param name="playerID"></param>
		/// <param name="unitID"></param>
		/// <returns></returns>
		private int F0_1403_4562(int playerID, int unitID)
		{
			//this.oCPU.Log.EnterBlock("'Fn9'(Cdecl, Far, Return) at 0x4562");

			// Local variables
			int Local_2;
			int Local_4;
			int Local_6;
			int Local_8;
			int Local_a;

			// function body
			Local_6 = this.parent.GameData.Players[playerID].Units[unitID].NextUnitID;

			if (Local_6 == -1)
			{
				return unitID;
			}
			else
			{
				Local_2 = unitID;
				Local_8 = 999;

				for (Local_a = 0; Local_a < 16; Local_a++)
				{
					if (this.parent.GameData.Units[(int)this.parent.GameData.Players[playerID].Units[Local_6].UnitType].MovementType != UnitMovementTypeEnum.Air)
					{
						if (Local_6 > unitID)
						{
							Local_4 = Local_6 - unitID;
						}
						else
						{
							Local_4 = (Local_6 - unitID) + 128;
						}

						if (Local_4 < Local_8)
						{
							Local_8 = Local_4;
							Local_2 = Local_6;
						}
					}

					Local_6 = this.parent.GameData.Players[playerID].Units[Local_6].NextUnitID;

					if (Local_6 == unitID)
						break;
				}

				return Local_2;
			}
		}
	}
}
