using System;
using System.Numerics;
using IRB.VirtualCPU;
using OpenCivOne.Graphics;
using OpenCivOne.Runtime;

namespace OpenCivOne
{
	public readonly record struct ClassicCombatForecast(
		int AttackStrength,
		int DefenseStrength,
		double AttackerWinProbability)
	{
		public static bool IsAvailable(
			ClassicAiProfile profile) =>
			ClassicAiRuntimeProfiles
				.UsesSmartEnhancements(profile);

		public static bool IsAvailable(
			ClassicAiProfile profile,
			UnitTypeEnum attackerType) =>
			attackerType != UnitTypeEnum.Nuclear &&
			IsAvailable(profile);

		public int ApproximateWinPercent =>
			(int)Math.Round(
				this.AttackerWinProbability * 100.0,
				MidpointRounding.AwayFromZero);
	}

	public class AttackActions
	{
		private static readonly BigInteger RngRawOutcomeCount =
			BigInteger.One << 32;
		private static readonly double RngPairOutcomeCount =
			Math.Pow(2.0, 64);

		private readonly record struct CombatSetup(
			UnitTypeEnum AttackerType,
			UnitTypeEnum DefenderType,
			int AttackedCityID,
			bool BarbarianCityAttack,
			int AttackStrength,
			int DefenseStrength);

		private OpenCivOneGame oParent;
		private VCPU oCPU;

		public AttackActions(OpenCivOneGame parent)
		{
			this.oParent = parent;
			this.oCPU = parent.CPU;
		}

		public ClassicCombatForecast GetCombatForecast(
			int attackerPlayerID,
			int attackerUnitID,
			int defenderPlayerID,
			int defenderUnitID)
		{
			CombatSetup setup = CalculateCombatSetup(
				attackerPlayerID,
				attackerUnitID,
				defenderPlayerID,
				defenderUnitID,
				applyResolutionDifficultyModifiers: true);
			double winProbability = CalculateStrictWinProbability(
				setup.AttackStrength,
				setup.DefenseStrength);
			if (setup.BarbarianCityAttack)
			{
				winProbability *=
					CalculateNotLessProbability(
						setup.AttackStrength,
						setup.DefenseStrength);
			}

			return new ClassicCombatForecast(
				setup.AttackStrength,
				setup.DefenseStrength,
				winProbability);
		}

		/// <summary>
		/// Player 1, unit 1 attacks unit 2 from player 2
		/// </summary>
		/// <param name="playerID1"></param>
		/// <param name="unitID1"></param>
		/// <param name="playerID2"></param>
		/// <param name="unitID2"></param>
		/// <param name="flag"></param>
		/// <returns>Attack result</returns>
		public int F0_29f3_000e_AttackUnit(int playerID1, int unitID1, int playerID2, int unitID2, bool flag)
			=> F0_29f3_000e_AttackUnit(
				playerID1,
				unitID1,
				playerID2,
				unitID2,
				flag,
				beginWorldMapAnimation: null,
				endWorldMapAnimation: null);

		internal int F0_29f3_000e_AttackUnit(
			int playerID1,
			int unitID1,
			int playerID2,
			int unitID2,
			bool flag,
			Action? beginWorldMapAnimation,
			Action? endWorldMapAnimation) =>
			F0_29f3_000e_AttackUnitWithPresentation(
				playerID1,
				unitID1,
				playerID2,
				unitID2,
				flag,
				beginWorldMapAnimation,
				endWorldMapAnimation,
				runWorldMapAnimation: null,
				runWorldMapModal: null);

		internal int F0_29f3_000e_AttackUnitWithPresentation(
			int playerID1,
			int unitID1,
			int playerID2,
			int unitID2,
			bool flag,
			Action? beginWorldMapAnimation,
			Action? endWorldMapAnimation,
			Action<Action>? runWorldMapAnimation,
			Func<Func<int>, int>? runWorldMapModal)
		{
			//this.oCPU.Log.EnterBlock($"F0_29f3_000e({playerID1}, {unitID1}, {playerID2}, {unitID2}, {flag})");

			// function body
			CombatSetup setup = CalculateCombatSetup(
				playerID1,
				unitID1,
				playerID2,
				unitID2,
				applyResolutionDifficultyModifiers: flag);
			UnitTypeEnum unit1Type = setup.AttackerType;
			UnitTypeEnum unit2Type = setup.DefenderType;
			int attackedCityID = setup.AttackedCityID;
			bool barbarianCityAttack =
				setup.BarbarianCityAttack;
			int attackStrength = setup.AttackStrength;
			int defenseStrength = setup.DefenseStrength;

			if (!flag)
			{
				return (attackStrength * 8) / (defenseStrength + 1);
			}

			if (playerID1 == this.oParent.GameData.HumanPlayerID &&
				F0_29f3_0c9e_ConfirmAttackAction(
					playerID2,
					runWorldMapModal) == -1)
			{
				this.oParent.GameData.Players[playerID1].Units[unitID1].GoToDestination = OpenCivOneGame.InvalidPosition;

				return -1;
			}
		
			int local_24 = 0;

			if (this.oParent.CAPI.RNG.Next(attackStrength) > this.oParent.CAPI.RNG.Next(defenseStrength))
			{
				local_24 = 16;
			}

			if (barbarianCityAttack && local_24 != 0 && this.oParent.CAPI.RNG.Next(attackStrength) < this.oParent.CAPI.RNG.Next(defenseStrength))
			{
				local_24 = 0;
			}

			ushort humanPlayerVisibilityMask = (ushort)(0x1 << this.oParent.GameData.HumanPlayerID);
			Unit attackingUnit = this.oParent.GameData.Players[playerID1].Units[unitID1];
			Unit defendingUnit = this.oParent.GameData.Players[playerID2].Units[unitID2];
			bool attackerCellKnownToHuman =
				(this.oParent.GameData.MapVisibility[attackingUnit.Position.X, attackingUnit.Position.Y] &
					humanPlayerVisibilityMask) != 0;
			bool defenderCellKnownToHuman =
				(this.oParent.GameData.MapVisibility[defendingUnit.Position.X, defendingUnit.Position.Y] &
					humanPlayerVisibilityMask) != 0;
			bool combatUnitVisibleToHuman =
				(attackingUnit.VisibleByPlayer & humanPlayerVisibilityMask) != 0 ||
				(defendingUnit.VisibleByPlayer & humanPlayerVisibilityMask) != 0;

			if (playerID1 == this.oParent.GameData.HumanPlayerID ||
				playerID2 == this.oParent.GameData.HumanPlayerID ||
				this.oParent.Var_d806_DebugFlag ||
				(combatUnitVisibleToHuman && attackerCellKnownToHuman && defenderCellKnownToHuman))
			{
				beginWorldMapAnimation?.Invoke();
				try
				{
				// Instruction address 0x29f3:0x03de, size: 5
				this.oParent.UnitManagement.F0_1866_16a9_CenterMap(this.oParent.GameData.HumanPlayerID,
					this.oParent.GameData.Players[playerID2].Units[unitID2].Position.X, this.oParent.GameData.Players[playerID2].Units[unitID2].Position.Y);

				// Instruction address 0x29f3:0x0407, size: 5
				if (this.oParent.MapManagement.F0_2aea_03ba_DrawCell(this.oParent.GameData.Players[playerID1].Units[unitID1].Position.X,
					this.oParent.GameData.Players[playerID1].Units[unitID1].Position.Y))
				{
					bool local_16 = false;

					if ((local_24 == 0 && (this.oParent.GameData.Units[(int)unit2Type].AttackStrength > 4 ||
							this.oParent.GameData.Units[(int)unit2Type].DefenseStrength > 2)) ||
						this.oParent.GameData.Units[(int)unit1Type].AttackStrength > 4 ||
						this.oParent.GameData.Units[(int)unit1Type].DefenseStrength > 2)
					{
						local_16 = true;
					}

					if (local_24 != 0 && unit1Type == UnitTypeEnum.Bomber)
					{
						// Instruction address 0x29f3:0x04ae, size: 5
						this.oParent.CommonTools.PlayTune(43, 0);
					}
					else
					{
						if ((local_24 == 0 || playerID1 != this.oParent.GameData.HumanPlayerID) &&
							(local_24 != 0 || playerID2 != this.oParent.GameData.HumanPlayerID))
						{
							if (local_16)
							{
								// Instruction address 0x29f3:0x04ae, size: 5
								this.oParent.CommonTools.PlayTune(41, 0);
							}
							else
							{
								// Instruction address 0x29f3:0x04ae, size: 5
								this.oParent.CommonTools.PlayTune(39, 0);
							}
						}
						else
						{
							if (local_16)
							{
								// Instruction address 0x29f3:0x04ae, size: 5
								this.oParent.CommonTools.PlayTune(40, 0);
							}
							else
							{
								// Instruction address 0x29f3:0x04ae, size: 5
								this.oParent.CommonTools.PlayTune(38, 0);
							}
						}
					}

					// Instruction address 0x29f3:0x04bc, size: 5
					this.oParent.MapManagement.F0_2aea_0e29_DrawUnit(playerID2, unitID2);

					if (this.oParent.GameData.Players[playerID1].Units[unitID1].NextUnitID != -1)
					{
						// Instruction address 0x29f3:0x04e4, size: 5
						this.oParent.MapManagement.F0_2aea_0e29_DrawUnit(playerID1, this.oParent.GameData.Players[playerID1].Units[unitID1].NextUnitID);
					}

					// Instruction address 0x29f3:0x050a, size: 5
					this.oParent.Graphics.F0_VGA_07d8_DrawImage(this.oParent.Var_aa_Screen0_Rectangle, 80, 0, 240, 200, this.oParent.Var_19d4_Screen1_Rectangle, 80, 0);

					// Instruction address 0x29f3:0x052d, size: 5
					int newXWindow = this.oParent.MapManagement.AdjustXPosition(this.oParent.GameData.Players[playerID1].Units[unitID1].Position.X - this.oParent.Var_d4cc_MapViewX) * 16 + 80;
					int newYWindow = (this.oParent.GameData.Players[playerID1].Units[unitID1].Position.Y - this.oParent.Var_d75e_MapViewY) * 16 + 8;

					int xStep = Math.Sign(this.oParent.GameData.Players[playerID2].Units[unitID2].Position.X - this.oParent.GameData.Players[playerID1].Units[unitID1].Position.X);
					int yStep = Math.Sign(this.oParent.GameData.Players[playerID2].Units[unitID2].Position.Y - this.oParent.GameData.Players[playerID1].Units[unitID1].Position.Y);

					// Always false
					if (this.oParent.GameData.Players[playerID2].Units[unitID2].Position.X != 0 ||
						this.oParent.GameData.Players[playerID1].Units[unitID1].Position.X != 79) goto L05a3;

					xStep = -xStep;
					goto L05d9;

				L05a3:
					// Always false
					if (this.oParent.GameData.Players[playerID1].Units[unitID1].Position.X != 0 ||
						this.oParent.GameData.Players[playerID2].Units[unitID2].Position.X != 79) goto L05d9;

					xStep = -xStep;
					goto L05d9;

				L05d9:
					for (int i = 0; i < 11; i++)
					{
						int cellX = (i * xStep) + newXWindow;
						int cellY = (i * yStep) + newYWindow;

						// Instruction address 0x29f3:0x061e, size: 5
						this.oParent.Graphics.F0_VGA_0c3e_DrawBitmapToScreen(this.oParent.Var_aa_Screen0_Rectangle,
							cellX + 1, cellY + 1,
							this.oParent.Array_d4ce[64 + (int)this.oParent.GameData.Players[playerID1].Units[unitID1].UnitType + (playerID1 * 32)]);

						// Instruction address 0x29f3:0x062a, size: 5
						this.oParent.CommonTools.WaitTimer(2);

						// Instruction address 0x29f3:0x0643, size: 5
						this.oParent.Graphics.F0_VGA_07d8_DrawImage(this.oParent.Var_19d4_Screen1_Rectangle,
							cellX, cellY, 16, 16, this.oParent.Var_aa_Screen0_Rectangle, cellX, cellY);
					}

					// Instruction address 0x29f3:0x0670, size: 5
					this.oParent.MapManagement.F0_2aea_11d4_DrawCellWithUnit(
						this.oParent.GameData.Players[playerID1].Units[unitID1].Position.X, this.oParent.GameData.Players[playerID1].Units[unitID1].Position.Y);

					// Instruction address 0x29f3:0x0694, size: 5
					this.oParent.MapManagement.F0_2aea_11d4_DrawCellWithUnit(
						this.oParent.GameData.Players[playerID2].Units[unitID2].Position.X, this.oParent.GameData.Players[playerID2].Units[unitID2].Position.Y);

					// Instruction address 0x29f3:0x06b4, size: 5
					this.oParent.Graphics.F0_VGA_07d8_DrawImage(this.oParent.Var_aa_Screen0_Rectangle, 0, 0, 256, 200, this.oParent.Var_19d4_Screen1_Rectangle, 0, 0);

					for (int i = 0; i < 8; i++)
					{
						int cellX = (local_24 * xStep) + newXWindow;
						int cellY = (local_24 * yStep) + newYWindow;

						// Instruction address 0x29f3:0x06e6, size: 5
						this.oParent.Graphics.F0_VGA_0c3e_DrawBitmapToScreen(this.oParent.Var_aa_Screen0_Rectangle,
							cellX + 1, cellY + 1, this.oParent.Array_d4ce[32 + i]);

						// Instruction address 0x29f3:0x06f2, size: 5
						this.oParent.CommonTools.WaitTimer(4);

						// Instruction address 0x29f3:0x070b, size: 5
						this.oParent.Graphics.F0_VGA_07d8_DrawImage(this.oParent.Var_19d4_Screen1_Rectangle,
							cellX, cellY, 16, 16, this.oParent.Var_aa_Screen0_Rectangle, cellX, cellY);
					}
				}
				}
				finally
				{
					endWorldMapAnimation?.Invoke();
				}
			}

			this.oParent.GameData.Players[playerID1].Diplomacy[playerID2] |= DiplomacyFlagsEnum.Unknown20;
			this.oParent.GameData.Players[playerID2].Diplomacy[playerID1] |= DiplomacyFlagsEnum.Unknown20;

			if (playerID1 != 0 && playerID2 != 0)
			{
				this.oParent.GameData.PeaceTurnCount = 0;
			}

			if ((playerID2 == this.oParent.GameData.HumanPlayerID &&
				this.oParent.GameData.Players[playerID2].Diplomacy[playerID1].HasFlag(DiplomacyFlagsEnum.Peace)) ||
				this.oParent.GameData.Players[playerID1].Diplomacy[playerID2].HasFlag(DiplomacyFlagsEnum.Unknown200))
			{
				this.oParent.Var_2f9e_MessageBoxStyle = MenuBoxReportTypeEnum.DefenseMinisterReport;

				// Instruction address 0x29f3:0x07c9, size: 5
				RunWorldMapModal(
					runWorldMapModal,
					() => this.oParent.Segment_1238.F0_1238_001e_ShowDialog($"Sneak attack by\n{this.oParent.GameData.Players[playerID1].Nationality} forces!\n", 100, 80));

				this.oParent.GameData.Players[playerID1].Diplomacy[playerID2] |= DiplomacyFlagsEnum.Unknown200;
				this.oParent.GameData.Players[playerID1].Diplomacy[playerID2] ^= DiplomacyFlagsEnum.Unknown200;
			}

			if (this.oParent.GameData.Players[playerID2].Diplomacy[playerID1].HasFlag(DiplomacyFlagsEnum.Peace) ||
				this.oParent.GameData.Players[playerID1].Diplomacy[playerID2].HasFlag(DiplomacyFlagsEnum.Peace))
			{
				if (playerID1 == this.oParent.GameData.HumanPlayerID || playerID2 == this.oParent.GameData.HumanPlayerID)
				{
					this.oParent.Var_2f9e_MessageBoxStyle = MenuBoxReportTypeEnum.ForeignMinisterReport;

					// Instruction address 0x29f3:0x0872, size: 5
					RunWorldMapModal(
						runWorldMapModal,
						() => this.oParent.Segment_1238.F0_1238_001e_ShowDialog(
							$"{this.oParent.GameData.Players[playerID2].Nation} cancel\npeace treaty\nwith {this.oParent.GameData.Players[playerID1].Nation}.\n", 100, 80));
				}

				if (playerID1 == this.oParent.GameData.HumanPlayerID)
				{
					if (this.oParent.GameData.Players[playerID2].Diplomacy[playerID1].HasFlag(DiplomacyFlagsEnum.Peace))
					{
						this.oParent.GameData.Players[playerID2].Diplomacy[playerID1] |= DiplomacyFlagsEnum.Vendetta;
					}
				}

				// Instruction address 0x29f3:0x08a6, size: 5
				this.oParent.Segment_2517.F0_2517_0aa1_ClearDiplomacyFlags(playerID1, playerID2, DiplomacyFlagsEnum.Peace);
			}

			if (playerID1 == this.oParent.GameData.HumanPlayerID)
			{
				this.oParent.GameData.Players[playerID2].Diplomacy[playerID1] |= DiplomacyFlagsEnum.Unknown200;
				this.oParent.GameData.Players[playerID2].Diplomacy[playerID1] ^= DiplomacyFlagsEnum.Unknown200;
			}

			if (unit1Type == UnitTypeEnum.Nuclear)
			{
				// Instruction address 0x29f3:0x08ed, size: 3
				F0_29f3_0d4d_NuclearAttackWithPresentation(
					playerID1,
					this.oParent.GameData.Players[playerID2].Units[unitID2].Position.X,
					this.oParent.GameData.Players[playerID2].Units[unitID2].Position.Y,
					runWorldMapAnimation,
					runWorldMapModal);

				return 1;
			}

			if (local_24 != 0)
			{
				if (playerID2 == 0)
				{
					if (this.oParent.GameData.Players[playerID2].Units[unitID2].UnitType == UnitTypeEnum.Diplomat)
					{
						this.oParent.GameData.Players[playerID1].Coins += 100;

						if (playerID1 == this.oParent.GameData.HumanPlayerID)
						{
							// Instruction address 0x29f3:0x094b, size: 5
							RunWorldMapModal(
								runWorldMapModal,
								() => this.oParent.Segment_1238.F0_1238_001e_ShowDialog(this.oParent.LanguageTools.F0_2f4d_044f_GetTextFromKingSection("*LEADER"), 80, 80));
						}
					}
				}

				if (attackedCityID == -1)
				{
					if (!this.oParent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(
						this.oParent.GameData.Players[playerID2].Units[unitID2].Position.X, this.oParent.GameData.Players[playerID2].Units[unitID2].Position.Y).HasFlag(TerrainImprovementFlagsEnum.Fortress))
					{
						int stackUnitCount = this.oParent.UnitManagement.F0_1866_1251_GetStackUnitValueSum(playerID2, unitID2, UnitStackValueTypeEnum.UnitCount);

						this.oParent.GameData.Players[playerID1].UnitsDestroyed[playerID2] += (short)stackUnitCount;

						// Instruction address 0x29f3:0x09ba, size: 5
						this.oParent.UnitManagement.F0_1866_0f10_DeleteUnitStack(playerID2, unitID2);

						if (stackUnitCount > 1)
						{
							if (playerID1 == this.oParent.GameData.HumanPlayerID || playerID2 == this.oParent.GameData.HumanPlayerID)
							{
								// Instruction address 0x29f3:0x0a19, size: 5
								RunWorldMapModal(
									runWorldMapModal,
									() => this.oParent.Segment_1238.F0_1238_001e_ShowDialog($"{stackUnitCount} units destroyed.\n", 80, 80));
							}
						}
					}
					else
					{
						// Instruction address 0x29f3:0x0ad8, size: 5
						this.oParent.UnitManagement.F0_1866_0f10_DeleteUnit(playerID2, unitID2);

						this.oParent.GameData.Players[playerID1].UnitsDestroyed[playerID2]++;
					}
				}
				else
				{
					if (this.oParent.GameData.Players[playerID2].Units[unitID2].NextUnitID == -1)
					{
						for (int i = 8; i >= 0; i--)
						{
							GPoint direction = this.oParent.MoveDirections[i];

							int newX = this.oParent.GameData.Players[playerID2].Units[unitID2].Position.X + direction.X;
							int newY = this.oParent.GameData.Players[playerID2].Units[unitID2].Position.Y + direction.Y;

							// Instruction address 0x29f3:0x0a7f, size: 5
							int activeUnitID = this.oParent.MapManagement.F0_2aea_1458_GetCellActiveUnitID(newX, newY);
							int activeUnitPlayerID = this.oParent.MapManagement.F0_2aea_14e0_GetCellActiveUnitPlayerID(newX, newY);

							if (activeUnitID != -1 && activeUnitPlayerID != this.oParent.GameData.HumanPlayerID)
							{
								// Instruction address 0x29f3:0x0aa7, size: 5
								this.oParent.UnitManagement.F0_1866_1593_UnitStack(activeUnitPlayerID, activeUnitID);
							}
						}

						if (this.oParent.GameData.Cities[attackedCityID].PlayerID == this.oParent.GameData.HumanPlayerID)
						{
							// Instruction address 0x29f3:0x0aca, size: 5
							this.oParent.AIEngine.F0_25fb_3e9c_MoveTransportNearEnemyCity(attackedCityID);
						}
					}

					// Instruction address 0x29f3:0x0ad8, size: 5
					this.oParent.UnitManagement.F0_1866_0f10_DeleteUnit(playerID2, unitID2);

					this.oParent.GameData.Players[playerID1].UnitsDestroyed[playerID2]++;
				}

				if (this.oParent.CAPI.RNG.Next(2) == 0)
				{
					return 1;
				}

				this.oParent.GameData.Players[playerID1].Units[unitID1].Status |= UnitStatusEnum.Veteran;

				return 1;
			}

			this.oParent.GameData.Players[playerID2].UnitsDestroyed[playerID1]++;

			// Instruction address 0x29f3:0x0b31, size: 5
			this.oParent.UnitManagement.F0_1866_0f10_DeleteUnit(playerID1, unitID1);

			if (this.oParent.CAPI.RNG.Next(2) != 0)
			{
				this.oParent.GameData.Players[playerID2].Units[unitID2].Status |= UnitStatusEnum.Veteran;
			}
		
			return 0;
		}

		private CombatSetup CalculateCombatSetup(
			int playerID1,
			int unitID1,
			int playerID2,
			int unitID2,
			bool applyResolutionDifficultyModifiers)
		{
			Unit unit1 =
				this.oParent.GameData.Players[playerID1]
					.Units[unitID1];
			Unit unit2 =
				this.oParent.GameData.Players[playerID2]
					.Units[unitID2];
			UnitTypeEnum unit1Type = unit1.UnitType;
			UnitTypeEnum unit2Type = unit2.UnitType;
			TerrainTypeEnum defenderTerrainType =
				this.oParent.MapManagement.GetTerrainType(
					unit2.Position.X,
					unit2.Position.Y);
			TerrainImprovementFlagsEnum defenderImprovements =
				this.oParent.MapManagement
					.F0_2aea_1585_GetVisibleTerrainImprovements(
						unit2.Position.X,
						unit2.Position.Y);
			bool barbarianCityAttack = false;
			int attackStrength =
				this.oParent.GameData.Units[(int)unit1Type]
					.AttackStrength * 8;
			int defenseStrength;

			if (defenderImprovements.HasFlag(
				TerrainImprovementFlagsEnum.Fortress))
			{
				defenseStrength =
					(this.oParent.GameData.Terrains[
						(int)defenderTerrainType].DefenseBonus *
					this.oParent.GameData.Units[
						(int)unit2Type].DefenseStrength) * 8;
			}
			else if (unit2.Status.HasFlag(
				UnitStatusEnum.Fortified))
			{
				defenseStrength =
					(this.oParent.GameData.Terrains[
						(int)defenderTerrainType].DefenseBonus *
					this.oParent.GameData.Units[
						(int)unit2Type].DefenseStrength) * 6;
			}
			else
			{
				defenseStrength =
					(this.oParent.GameData.Terrains[
						(int)defenderTerrainType].DefenseBonus *
					this.oParent.GameData.Units[
						(int)unit2Type].DefenseStrength) * 4;
			}

			if (playerID1 == 0)
			{
				attackStrength =
					playerID2 ==
						this.oParent.GameData.HumanPlayerID
						? (attackStrength *
							(this.oParent.GameData
								.DifficultyLevel + 1)) / 4
						: attackStrength / 2;
			}

			UnitDefinition defenderDefinition =
				this.oParent.GameData.Units[(int)unit2Type];
			if (defenderDefinition.MovementType is
				UnitMovementTypeEnum.Air or
				UnitMovementTypeEnum.Water)
			{
				defenseStrength =
					defenderDefinition.DefenseStrength * 8;
			}

			int attackedCityID = -1;
			if (defenderImprovements.HasFlag(
				TerrainImprovementFlagsEnum.City))
			{
				attackedCityID =
					this.oParent.Tools
						.F0_2dc4_00ba_GetCityByLocation(
							unit2.Position.X,
							unit2.Position.Y);
				if (this.oParent.GameData.Cities[attackedCityID]
						.HasImprovement(ImprovementEnum.CityWalls) &&
					this.oParent.GameData.Units[(int)unit1Type]
						.AttackStrength != 12 &&
					defenderDefinition.MovementType !=
						UnitMovementTypeEnum.Air)
				{
					defenseStrength =
						(this.oParent.GameData.Terrains[
							(int)defenderTerrainType].DefenseBonus *
						defenderDefinition.DefenseStrength) * 12;
				}

				if (playerID1 == 0)
				{
					if (this.oParent.GameData.Players[playerID2]
						.CityCount == 1)
					{
						attackStrength = 0;
					}
					if (this.oParent.GameData.Cities[attackedCityID]
						.HasImprovement(ImprovementEnum.Palace))
					{
						attackStrength /= 2;
					}
					barbarianCityAttack = true;
				}
			}

			if (unit1.Status.HasFlag(UnitStatusEnum.Veteran))
			{
				attackStrength += attackStrength / 2;
			}
			if (unit2.Status.HasFlag(UnitStatusEnum.Veteran))
			{
				defenseStrength += defenseStrength / 2;
			}
			if (unit1.RemainingMoves < 3)
			{
				attackStrength =
					(unit1.RemainingMoves * attackStrength) / 3;
			}

			if (applyResolutionDifficultyModifiers &&
				playerID1 != 0)
			{
				if (this.oParent.GameData.DifficultyLevel <= 1 &&
					playerID2 ==
						this.oParent.GameData.HumanPlayerID)
				{
					attackStrength /= 2;
				}
				if (this.oParent.GameData.DifficultyLevel == 0 &&
					playerID1 ==
						this.oParent.GameData.HumanPlayerID)
				{
					attackStrength *= 2;
				}
			}

			return new CombatSetup(
				unit1Type,
				unit2Type,
				attackedCityID,
				barbarianCityAttack,
				attackStrength,
				defenseStrength);
		}

		private static double CalculateStrictWinProbability(
			int attackStrength,
			int defenseStrength)
		{
			int attackOutcomes = Math.Max(1, attackStrength);
			int defenseOutcomes = Math.Max(1, defenseStrength);
			BigInteger winningRawPairs = BigInteger.Zero;

			for (int attackRoll = 0;
				attackRoll < attackOutcomes;
				attackRoll++)
			{
				BigInteger attackBucketSize =
					GetRngBucketSize(
						attackOutcomes,
						attackRoll);
				BigInteger lowerDefenseRawOutcomes =
					GetCumulativeRngBucketSize(
						defenseOutcomes,
						attackRoll);
				winningRawPairs +=
					attackBucketSize *
					lowerDefenseRawOutcomes;
			}

			return (double)winningRawPairs /
				RngPairOutcomeCount;
		}

		private static double CalculateNotLessProbability(
			int attackStrength,
			int defenseStrength)
		{
			int attackOutcomes = Math.Max(1, attackStrength);
			int defenseOutcomes = Math.Max(1, defenseStrength);
			BigInteger nonLosingRawPairs = BigInteger.Zero;

			for (int attackRoll = 0;
				attackRoll < attackOutcomes;
				attackRoll++)
			{
				BigInteger attackBucketSize =
					GetRngBucketSize(
						attackOutcomes,
						attackRoll);
				BigInteger noGreaterDefenseRawOutcomes =
					GetCumulativeRngBucketSize(
						defenseOutcomes,
						attackRoll + 1);
				nonLosingRawPairs +=
					attackBucketSize *
					noGreaterDefenseRawOutcomes;
			}

			return (double)nonLosingRawPairs /
				RngPairOutcomeCount;
		}

		private static BigInteger GetRngBucketSize(
			int outcomeCount,
			int outcome)
		{
			return GetCumulativeRngBucketSize(
					outcomeCount,
					outcome + 1) -
				GetCumulativeRngBucketSize(
					outcomeCount,
					outcome);
		}

		private static BigInteger GetCumulativeRngBucketSize(
			int outcomeCount,
			int exclusiveOutcome)
		{
			if (exclusiveOutcome <= 0)
			{
				return BigInteger.Zero;
			}
			if (exclusiveOutcome >= outcomeCount)
			{
				return RngRawOutcomeCount;
			}

			BigInteger numerator =
				(BigInteger)exclusiveOutcome *
				RngRawOutcomeCount;
			return BigInteger.DivRem(
					numerator,
					outcomeCount,
					out BigInteger remainder) +
				(remainder.IsZero
					? BigInteger.Zero
					: BigInteger.One);
		}

		/// <summary>
		/// Adds unit to new or existing stack
		/// !!! To Do: Check if stack overflows!
		/// </summary>
		/// <param name="playerID"></param>
		/// <param name="unitID"></param>
		/// <param name="nextUnitID"></param>
		public void F0_29f3_0b66_AddUnitToStack(int playerID, int unitID, int nextUnitID)
		{
			//this.oCPU.Log.EnterBlock($"F0_29f3_0b66({playerID}, {unitID}, {nextUnitID})");

			// function body
			if (this.oParent.GameData.Players[playerID].Units[nextUnitID].NextUnitID == -1)
			{
				this.oParent.GameData.Players[playerID].Units[nextUnitID].NextUnitID = (short)unitID;
				this.oParent.GameData.Players[playerID].Units[unitID].NextUnitID = (short)nextUnitID;
			}
			else
			{
				this.oParent.GameData.Players[playerID].Units[unitID].NextUnitID = this.oParent.GameData.Players[playerID].Units[nextUnitID].NextUnitID;
				this.oParent.GameData.Players[playerID].Units[nextUnitID].NextUnitID = (short)unitID;
			}
		}

		/// <summary>
		/// Remove unit from stack
		/// </summary>
		/// <param name="playerID"></param>
		/// <param name="unitID"></param>
		public void F0_29f3_0bc9_RemoveUnitFromStack(int playerID, int unitID)
		{
			//this.oCPU.Log.EnterBlock($"F0_29f3_0bc9({playerID}, {unitID})");

			// function body
			short nextUnitID = this.oParent.GameData.Players[playerID].Units[unitID].NextUnitID;

			if (this.oParent.GameData.Players[playerID].Units[unitID].NextUnitID != -1)
			{
				if (this.oParent.GameData.Players[playerID].Units[nextUnitID].NextUnitID == unitID)
				{
					this.oParent.GameData.Players[playerID].Units[nextUnitID].NextUnitID = -1;
				}
				else
				{
					int count = 0;

					do
					{
						nextUnitID = this.oParent.GameData.Players[playerID].Units[nextUnitID].NextUnitID;
						count++;
					} while (nextUnitID != -1 && count < UnitManagement.ActiveUnitCapacity &&
						this.oParent.GameData.Players[playerID].Units[nextUnitID].NextUnitID != unitID);

					if (count < UnitManagement.ActiveUnitCapacity && nextUnitID != -1)
					{
						this.oParent.GameData.Players[playerID].Units[nextUnitID].NextUnitID = this.oParent.GameData.Players[playerID].Units[unitID].NextUnitID;
					}
				}

				this.oParent.GameData.Players[playerID].Units[unitID].NextUnitID = -1;
			}
		}

		/// <summary>
		/// Confirms attack action against leader with whom there is a peace treaty
		/// </summary>
		/// <param name="playerID">The player which is attacked</param>
		/// <returns></returns>
		public int F0_29f3_0c9e_ConfirmAttackAction(int playerID)
			=> F0_29f3_0c9e_ConfirmAttackAction(
				playerID,
				runWorldMapModal: null);

		private int F0_29f3_0c9e_ConfirmAttackAction(
			int playerID,
			Func<Func<int>, int>? runWorldMapModal)
		{
			//this.oCPU.Log.EnterBlock($"F0_29f3_0c9e({playerID})");

			// function body
			if (this.oParent.GameData.Players[this.oParent.GameData.HumanPlayerID].Diplomacy[playerID].HasFlag(DiplomacyFlagsEnum.Peace))
			{
				this.oParent.Var_2f9e_MessageBoxStyle = MenuBoxReportTypeEnum.ForeignMinisterReport;

				if (RunWorldMapModal(
					runWorldMapModal,
					() => this.oParent.Segment_1238.F0_1238_001e_ShowDialog(
						$"We have signed a\npeace treaty with\nthe {this.oParent.GameData.Players[playerID].Nation}!\n Cancel action.\n Break treaty.\n", 80, 80)) != 1)
				{
					return -1;
				}

				if (this.oParent.GameData.Players[this.oParent.GameData.HumanPlayerID].GovernmentType > 3)
				{
					this.oParent.Var_2f9e_MessageBoxStyle = MenuBoxReportTypeEnum.DomesticAdvisorReport;

					// Instruction address 0x29f3:0x0d39, size: 5
					RunWorldMapModal(
						runWorldMapModal,
						() => this.oParent.Segment_1238.F0_1238_001e_ShowDialog("Overruled by\nthe Senate.\nAction canceled.\n", 100, 80));

					return -1;
				}

				return 1;
			}

			return 0;
		}

		/// <summary>
		/// Attack with nuclear weapon
		/// </summary>
		/// <param name="playerID"></param>
		/// <param name="x"></param>
		/// <param name="y"></param>
		public void F0_29f3_0d4d_NuclearAttack(int playerID, int x, int y)
			=> F0_29f3_0d4d_NuclearAttackWithPresentation(
				playerID,
				x,
				y,
				runWorldMapAnimation: null,
				runWorldMapModal: null);

		internal void F0_29f3_0d4d_NuclearAttackWithPresentation(
			int playerID,
			int x,
			int y,
			Action<Action>? runWorldMapAnimation,
			Func<Func<int>, int>? runWorldMapModal)
		{
			//this.oCPU.Log.EnterBlock($"F0_29f3_0d4d({playerID}, {x}, {y})");

			// function body			
			if (playerID != this.oParent.GameData.HumanPlayerID)
			{
				this.oParent.Var_2f9e_MessageBoxStyle = MenuBoxReportTypeEnum.DefenseMinisterReport;

				// Instruction address 0x29f3:0x0d93, size: 5
				RunWorldMapModal(
					runWorldMapModal,
					() => this.oParent.Segment_1238.F0_1238_001e_ShowDialog($"{this.oParent.GameData.Players[playerID].Nation} use\nnuclear weapons!\n", 100, 80));
			}

			if (ShouldRenderNuclearAttack(playerID, x, y))
			{
				RunWorldMapAnimation(
					runWorldMapAnimation,
					() => this.oParent.Overlay_22.F22_0000_0967(x, y));
			}

			for (int i = 8; i >= 0; i--)
			{
				GPoint direction = this.oParent.MoveDirections[i];

				int newX = this.oParent.MapManagement.AdjustXPosition(x + direction.X);
				int newY = y + direction.Y;

				if (this.oParent.MapManagement.ValidateMapCoordinates(newX, newY))
				{
					// Instruction address 0x29f3:0x0dcb, size: 5
					int activeUnitID = this.oParent.MapManagement.F0_2aea_1458_GetCellActiveUnitID(newX, newY);
					int activeUnitPlayerID = this.oParent.MapManagement.F0_2aea_14e0_GetCellActiveUnitPlayerID(newX, newY);

					if (this.oParent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(newX, newY).HasFlag(TerrainImprovementFlagsEnum.City))
					{
						// Instruction address 0x29f3:0x0dee, size: 5
						int cityID = this.oParent.Tools.F0_2dc4_00ba_GetCityByLocation(newX, newY);

						if (this.oParent.GameData.Cities[cityID].HasImprovement(ImprovementEnum.SDIDefense))
						{
							// Instruction address 0x29f3:0x0e40, size: 5
							RunWorldMapModal(
								runWorldMapModal,
								() => this.oParent.Segment_1238.F0_1238_001e_ShowDialog($"SDI protects {this.oParent.Segment_2459.F0_2459_08c6_GetCityName(cityID)}.\n", 80, 100));

							activeUnitID = -1;
						}
					}

					if (activeUnitID != -1)
					{
						// Instruction address 0x29f3:0x0e5e, size: 5
						int unitCount = this.oParent.UnitManagement.F0_1866_1251_GetStackUnitValueSum(activeUnitPlayerID, activeUnitID, UnitStackValueTypeEnum.UnitCount);

						this.oParent.GameData.Players[playerID].UnitsDestroyed[activeUnitPlayerID] += (short)unitCount;

						// Instruction address 0x29f3:0x0e89, size: 5
						this.oParent.UnitManagement.F0_1866_0f10_DeleteUnitStack(activeUnitPlayerID, activeUnitID);

						if (playerID != activeUnitPlayerID)
						{
							this.oParent.GameData.Players[activeUnitPlayerID].Diplomacy[playerID] |= DiplomacyFlagsEnum.Vendetta | DiplomacyFlagsEnum.Unknown80;
						}
					}
				}
			}

			// Instruction address 0x29f3:0x0eb8, size: 3
			F0_29f3_0ec3_AddEffectsOfNuclearAttackOrCatastrophe(
				x,
				y,
				runWorldMapAnimation);
		}

		/// <summary>
		/// Add effects of nuclear attack or nuclear catastrophe to affected surrounding cells
		/// </summary>
		/// <param name="x"></param>
		/// <param name="y"></param>
		public void F0_29f3_0ec3_AddEffectsOfNuclearAttackOrCatastrophe(int x, int y)
			=> F0_29f3_0ec3_AddEffectsOfNuclearAttackOrCatastrophe(
				x,
				y,
				runWorldMapAnimation: null);

		private void F0_29f3_0ec3_AddEffectsOfNuclearAttackOrCatastrophe(
			int x,
			int y,
			Action<Action>? runWorldMapAnimation)
		{
			//this.oCPU.Log.EnterBlock($"F0_29f3_0ec3({xPos}, {yPos})");

			// function body
			// !!! To Do: Effects of nuclear attack should exceed more than one cell in each direction
			for (int i = 0; i < 9; i++)
			{
				GPoint direction = this.oParent.MoveDirections[i];

				// Instruction address 0x29f3:0x0f26, size: 5
				int newX = this.oParent.MapManagement.AdjustXPosition(x + direction.X);
				int newY = y + direction.Y;

				if (this.oParent.MapManagement.ValidateMapCoordinates(newX, newY))
				{
					if (this.oParent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(newX, newY).HasFlag(TerrainImprovementFlagsEnum.City))
					{
						// Instruction address 0x29f3:0x0f51, size: 5
						int cityID = this.oParent.Tools.F0_2dc4_00ba_GetCityByLocation(newX, newY);

						this.oParent.GameData.Cities[cityID].ActualSize -= (sbyte)(this.oParent.GameData.Cities[cityID].ActualSize / 2);
					}
					else
					{
						if (this.oParent.MapManagement.GetTerrainType(newX, newY) != TerrainTypeEnum.Water && this.oParent.CAPI.RNG.Next(3) != 0)
						{
							// Instruction address 0x29f3:0x0efa, size: 5
							this.oParent.CityWorker.F0_1d12_6d33_AddPollutionToCell(newX, newY);
						}
					}

					ushort humanPlayerVisibilityMask =
						(ushort)(1 << this.oParent.GameData.HumanPlayerID);
					if (this.oParent.Var_d806_DebugFlag ||
						(this.oParent.GameData.MapVisibility[newX, newY] &
							humanPlayerVisibilityMask) != 0)
					{
						// Instruction address 0x29f3:0x0f08, size: 5
						RunWorldMapAnimation(
							runWorldMapAnimation,
							() => this.oParent.MapManagement.F0_2aea_11d4_DrawCellWithUnit(newX, newY));
					}
				}
			}
		}

		private static int RunWorldMapModal(
			Func<Func<int>, int>? runWorldMapModal,
			Func<int> showModal) =>
			runWorldMapModal?.Invoke(showModal) ?? showModal();

		private static void RunWorldMapAnimation(
			Action<Action>? runWorldMapAnimation,
			Action showAnimation)
		{
			if (runWorldMapAnimation is null)
			{
				showAnimation();
				return;
			}

			runWorldMapAnimation(showAnimation);
		}

		private bool ShouldRenderNuclearAttack(int playerID, int x, int y)
		{
			if (playerID == this.oParent.GameData.HumanPlayerID ||
				this.oParent.Var_d806_DebugFlag ||
				this.oParent.MapManagement.F0_2aea_14e0_GetCellActiveUnitPlayerID(x, y) ==
					this.oParent.GameData.HumanPlayerID)
			{
				return true;
			}

			ushort humanPlayerVisibilityMask =
				(ushort)(1 << this.oParent.GameData.HumanPlayerID);
			for (int i = 0; i < 9; i++)
			{
				GPoint direction = this.oParent.MoveDirections[i];
				int newX = this.oParent.MapManagement.AdjustXPosition(
					x + direction.X);
				int newY = y + direction.Y;

				if (this.oParent.MapManagement.ValidateMapCoordinates(newX, newY) &&
					(this.oParent.GameData.MapVisibility[newX, newY] &
						humanPlayerVisibilityMask) != 0)
				{
					return true;
				}
			}

			return false;
		}
	}
}
