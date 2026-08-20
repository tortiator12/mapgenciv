using System;
using Avalonia.Media;
using IRB.VirtualCPU;
using OpenCivOne.Localization;

namespace OpenCivOne
{
	public class Replay
	{
		private OpenCivOneGame oParent;
		private VCPU oCPU;

		public Replay(OpenCivOneGame parent)
		{
			this.oParent = parent;
			this.oCPU = parent.CPU;
		}

		private string GetLocalizedNation(
			int playerID,
			bool useNationality = false)
		{
			Player player = this.oParent.GameData.Players[playerID];
			int nationalityID = player.NationalityID;
			string currentName = useNationality
				? player.Nationality
				: player.Nation;
			if (nationalityID < 0 ||
				nationalityID >= this.oParent.GameData.Nations.Length)
			{
				return currentName;
			}

			NationDefinition definition =
				this.oParent.GameData.Nations[nationalityID];
			return ClassicDisplayNames.Nation(
				nationalityID,
				currentName,
				useNationality
					? definition.Nationality
					: definition.Nation);
		}

		private static string GetLocalizedGovernment(int governmentType)
		{
			ClassicGameTextKey key = governmentType switch
			{
				0 => ClassicGameTextKey.ReportGovernmentAnarchy,
				1 => ClassicGameTextKey.ReportGovernmentDespotism,
				2 => ClassicGameTextKey.ReportGovernmentMonarchy,
				3 => ClassicGameTextKey.ReportGovernmentCommunist,
				4 => ClassicGameTextKey.ReportGovernmentRepublic,
				5 => ClassicGameTextKey.ReportGovernmentDemocratic,
				_ => ClassicGameTextKey.ReportGovernmentAnarchy
			};
			return ClassicGameText.Current[key];
		}

		private static string FormatReplayYear(int year)
		{
			return ClassicGameText.Current.Format(
				year < 0
					? ClassicGameTextKey.ReportYearBeforeCommonEra
					: ClassicGameTextKey.ReportYearCommonEra,
				Math.Abs(year));
		}

		private void AppendCityNameToReplayMessage(uint cityNameID)
		{
			string cityName =
				cityNameID < this.oParent.GameData.CityNames.Length
					? this.oParent.GameData.CityNames[cityNameID] ?? string.Empty
					: string.Empty;
			int embeddedTerminator = cityName.IndexOf('\0');
			int sourceLength =
				embeddedTerminator >= 0
					? embeddedTerminator
					: cityName.Length;
			int nameLength = Math.Min(0xd, sourceLength);
			ushort stringOffset =
				(ushort)(
					0xba06 +
					this.oParent.CAPI.strlen(0xba06));

			for (int i = 0; i < nameLength; i++)
			{
				this.oCPU.WriteUInt8(
					this.oCPU.DS.UInt16,
					(ushort)(stringOffset + i),
					(byte)cityName[i]);
			}

			this.oCPU.WriteUInt8(
				this.oCPU.DS.UInt16,
				(ushort)(stringOffset + nameLength),
				0);
		}

		/// <summary>
		/// ?
		/// </summary>
		public void F9_0000_0000()
		{
			this.oCPU.Log.EnterBlock("F9_0000_0000()");
			string[] originalPlayerNations =
				new string[this.oParent.GameData.Players.Length];
			string[] originalPlayerNationalities =
				new string[this.oParent.GameData.Players.Length];
			for (int i = 0; i < this.oParent.GameData.Players.Length; i++)
			{
				originalPlayerNations[i] =
					this.oParent.GameData.Players[i].Nation;
				originalPlayerNationalities[i] =
					this.oParent.GameData.Players[i].Nationality;
			}

			// function body
			this.oCPU.PUSH_UInt16(this.oCPU.BP.UInt16);
			this.oCPU.BP.UInt16 = this.oCPU.SP.UInt16;
			this.oCPU.SP.UInt16 = this.oCPU.SUB_UInt16(this.oCPU.SP.UInt16, 0x24);
			this.oCPU.PUSH_UInt16(this.oCPU.SI.UInt16);

		L0007:
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.DS.UInt16, 0x680e), 0x0);
			if (this.oCPU.Flags.NE) goto L0027;

			// Instruction address 0x0000:0x001a, size: 5
			this.oCPU.AX.Int16 = (short)this.oParent.Segment_1238.F0_1238_001e_ShowDialog(0x3fb0, 100, 80);

			this.oCPU.WriteUInt16(this.oCPU.DS.UInt16, 0x680a, this.oCPU.AX.UInt16);
			goto L002d;

		L0027:
			this.oCPU.WriteUInt16(this.oCPU.DS.UInt16, 0x680a, 0x4);

		L002d:
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.DS.UInt16, 0x680a), 0x0);
			if (this.oCPU.Flags.G) goto L0037;
			goto L089e;

		L0037:
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.DS.UInt16, 0x680a), 0x3);
			if (this.oCPU.Flags.NE) goto L0085;

			// Instruction address 0x0000:0x004a, size: 5
			this.oParent.CAPI.open("REPLAY.TXT", 0x8301, 0x80);

			this.oCPU.WriteUInt16(this.oCPU.DS.UInt16, 0x680c, this.oCPU.AX.UInt16);
			this.oCPU.CMP_UInt16(this.oCPU.AX.UInt16, 0xffff);
			if (this.oCPU.Flags.NE) goto L0081;

			// Instruction address 0x0000:0x0062, size: 5
			this.oParent.CAPI.strcpy(
				0xba06,
				ClassicGameText.Current[
					ClassicGameTextKey.ReplayFileError]);

			// Instruction address 0x0000:0x0076, size: 5
			this.oParent.Segment_1238.F0_1238_001e_ShowDialog(0xba06, 100, 80);

			goto L089e;

		L0081:
			F9_0000_0c30();

		L0085:
			this.oParent.Graphics.F0_VGA_07d8_DrawImage(this.oParent.Var_aa_Screen0_Rectangle, 0, 0, 320, 200, this.oParent.Var_19d4_Screen1_Rectangle, 0, 0);

			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe), 0x0);

		L0094:
			this.oCPU.BX.UInt16 = this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe));
			this.oCPU.BX.UInt16 = this.oCPU.SHL_UInt16(this.oCPU.BX.UInt16, 0x1);
			this.oCPU.ES.UInt16 = 0x3725; // segment
			this.oCPU.WriteUInt16(this.oCPU.ES.UInt16, (ushort)(this.oCPU.BX.UInt16 + 0x0), 0xffff);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe), this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe))));
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe)), 0x80);
			if (this.oCPU.Flags.L) goto L0094;
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe), 0x1);

		L00b3:
			this.oCPU.SI.UInt16 = this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe));
			this.oCPU.SI.UInt16 = this.oCPU.SHL_UInt16(this.oCPU.SI.UInt16, 0x1);

			this.oCPU.AX.UInt16 = (ushort)this.oParent.GameData.Players[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe))].NationalityID;
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 + this.oCPU.SI.UInt16 - 0x20), this.oCPU.AX.UInt16);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe), this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe))));
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe)), 0x8);
			if (this.oCPU.Flags.L) goto L00b3;
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe), 0x1);
			goto L00e8;

		L00cf:
			this.oCPU.AX.UInt16 = this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe));

		L00d2:
			this.oParent.GameData.Players[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe))].NationalityID = (short)this.oCPU.AX.UInt16;

			F9_0000_0d5d(this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe)));

		L00e5:
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe), 
				this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe))));

		L00e8:
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe)), 0x8);
			if (this.oCPU.Flags.GE) goto L010c;

			this.oCPU.AX.UInt16 = (ushort)this.oParent.GameData.HumanPlayerID;
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe)), this.oCPU.AX.UInt16);
			if (this.oCPU.Flags.E) goto L00e5;
			this.oCPU.AX.UInt16 = 0x1;
			this.oCPU.CX.LowUInt8 = this.oCPU.ReadUInt8(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe));
			this.oCPU.AX.UInt16 = this.oCPU.SHL_UInt16(this.oCPU.AX.UInt16, this.oCPU.CX.LowUInt8);
			this.oCPU.TEST_UInt16(this.oCPU.AX.UInt16, (ushort)this.oParent.GameData.PlayerIdentityFlags);
			if (this.oCPU.Flags.E) goto L00cf;
			this.oCPU.AX.UInt16 = this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe));
			this.oCPU.AX.UInt16 = this.oCPU.ADD_UInt16(this.oCPU.AX.UInt16, 0x8);
			goto L00d2;

		L010c:
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.DS.UInt16, 0x680a), 0x4);
			if (this.oCPU.Flags.E) goto L0191;

			// Instruction address 0x0000:0x0126, size: 5
			this.oParent.DrawTools.FillRectangle(this.oParent.Var_aa_Screen0_Rectangle, 0, 0, 320, 200, 0);

			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xc), 0x1);
			goto L0184;

		L0135:
			// Instruction address 0x0000:0x0155, size: 5
			this.oParent.DrawTools.FillRectangle(this.oParent.Var_aa_Screen0_Rectangle,
				this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xa)) * 4,
				(this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xc)) * 4) + 4,
				4, 4, 8);

		L0138:
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xa), this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xa))));

		L0160:
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xa)), 0x50);
			if (this.oCPU.Flags.GE) goto L0181;

			// Instruction address 0x0000:0x016c, size: 5
			this.oCPU.AX.Int16 = (short)this.oParent.MapManagement.GetTerrainType(
				this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xa)),
				this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xc)));

			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x22), this.oCPU.AX.UInt16);
			this.oCPU.CMP_UInt16(this.oCPU.AX.UInt16, 0xa);
			if (this.oCPU.Flags.NE) goto L0135;

			// Instruction address 0x0000:0x0155, size: 5
			this.oParent.DrawTools.FillRectangle(this.oParent.Var_aa_Screen0_Rectangle,
				this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xa)) * 4,
				(this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xc)) * 4) + 4,
				4, 4, 1);

			goto L0138;

		L0181:
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xc), this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xc))));

		L0184:
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xc)), 0x31);
			if (this.oCPU.Flags.GE) goto L0191;
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xa), 0x0);
			goto L0160;

		L0191:
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2), 0x0);

		L0196:
			this.oCPU.AX.UInt16 = (ushort)this.oParent.GameData.ReplayDataLength;
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2)), this.oCPU.AX.UInt16);
			if (this.oCPU.Flags.L) goto L01a1;
			goto L083d;

		L01a1:
			this.oCPU.AX.LowUInt8 = this.oParent.GameData.ReplayData[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))];
			this.oCPU.AX.HighUInt8 = 0;
			this.oCPU.AX.UInt16 = this.oCPU.AND_UInt16(this.oCPU.AX.UInt16, 0xf);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x24), this.oCPU.AX.UInt16);
			this.oCPU.AX.LowUInt8 = this.oParent.GameData.ReplayData[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))];
			this.oCPU.AX.HighUInt8 = 0;
			this.oCPU.CX.LowUInt8 = 0x4;
			this.oCPU.AX.UInt16 = this.oCPU.SHR_UInt16(this.oCPU.AX.UInt16, this.oCPU.CX.LowUInt8);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x6), this.oCPU.AX.UInt16);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2),
				this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))));

			this.oCPU.AX.LowUInt8 = this.oParent.GameData.ReplayData[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))];
			this.oCPU.AX.HighUInt8 = 0;
			this.oCPU.CX.HighUInt8 = this.oCPU.ReadUInt8(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x24));
			this.oCPU.CX.LowUInt8 = 0;
			this.oCPU.AX.UInt16 = this.oCPU.ADD_UInt16(this.oCPU.AX.UInt16, this.oCPU.CX.UInt16);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x24), this.oCPU.AX.UInt16);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2),
				this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))));

			this.oCPU.AX.Int16 =
				(short)this.oParent.Segment_1238.TurnCountToYear(
					this.oCPU.AX.Int16);

			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x4), this.oCPU.AX.UInt16);
			this.oCPU.WriteUInt16(this.oCPU.DS.UInt16, 0x6810, 0xffff);
			this.oCPU.WriteUInt8(this.oCPU.DS.UInt16, 0xba06, 0x0);

			// Instruction address 0x0000:0x0214, size: 5
			this.oParent.CAPI.strcat(
				0xba06,
				FormatReplayYear(
					this.oCPU.ReadInt16(
						this.oCPU.SS.UInt16,
						(ushort)(this.oCPU.BP.UInt16 - 0x4))));

			// Instruction address 0x0000:0x023f, size: 5
			this.oParent.CAPI.strcat(0xba06, ": ");

			this.oCPU.AX.UInt16 = this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x6));
			this.oCPU.AX.UInt16 = this.oCPU.SUB_UInt16(this.oCPU.AX.UInt16, 0x1);
			this.oCPU.CMP_UInt16(this.oCPU.AX.UInt16, 0xc);
			if (this.oCPU.Flags.BE) goto L0255;
			goto L0826;

		L0255:
			switch(this.oCPU.AX.UInt16)
			{
				case 0:
					goto L025d;
				case 1:
					goto L03ae;
				case 2:
					goto L0414;
				case 3:
					goto L0826;
				case 4:
					goto L0453;
				case 5:
					goto L04a8;
				case 6:
					goto L0826;
				case 7:
					goto L04fb;
				case 8:
					goto L025d;
				case 9:
					goto L054f;
				case 10:
					goto L05b9;
				case 11:
					goto L065c;
				case 12:
					goto L0779;
			}

		L025d:
			this.oCPU.AX.LowUInt8 = this.oParent.GameData.ReplayData[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))];
			this.oCPU.AX.HighUInt8 = 0;
			this.oCPU.WriteUInt16(this.oCPU.DS.UInt16, 0x6810, this.oCPU.AX.UInt16);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2),
				this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))));

			this.oCPU.AX.LowUInt8 = this.oParent.GameData.ReplayData[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))];
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x8), this.oCPU.AX.UInt16);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2),
				this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))));

			this.oCPU.AX.LowUInt8 = this.oParent.GameData.ReplayData[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))];
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xa), this.oCPU.AX.UInt16);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2),
				this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))));

			this.oCPU.AX.LowUInt8 = this.oParent.GameData.ReplayData[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))];
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xc), this.oCPU.AX.UInt16);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2),
				this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))));

			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.DS.UInt16, 0x6810), 0xff);
			if (this.oCPU.Flags.NE) goto L02a6;
			goto L0336;

		L02a6:
			// Instruction address 0x0000:0x02b4, size: 5
			this.oParent.CAPI.strcat(
				0xba06,
				GetLocalizedNation(
					this.oCPU.ReadInt16(
						this.oCPU.DS.UInt16,
						0x6810)));

			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x6)), 0x1);
			if (this.oCPU.Flags.NE) goto L02e2;

			// Instruction address 0x0000:0x02ca, size: 5
			this.oParent.CAPI.strcat(
				0xba06,
				ClassicGameText.Current[
					ClassicGameTextKey.ReplayFoundCityConnector]);

			F9_0000_09dc(
				this.oCPU.ReadUInt16(this.oCPU.DS.UInt16, 0x6810),
				this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xa)),
				this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xc)));

			goto L0300;

		L02e2:
			// Instruction address 0x0000:0x02ea, size: 5
			this.oParent.CAPI.strcat(
				0xba06,
				ClassicGameText.Current[
					ClassicGameTextKey.ReplayCaptureConnector]);

			F9_0000_0a22(
				this.oCPU.ReadUInt16(this.oCPU.DS.UInt16, 0x6810),
				this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xa)),
				this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xc)));

		L0300:
			uint uiCityNameID = this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x8));
			AppendCityNameToReplayMessage(uiCityNameID);

			F9_0000_08a3();

			goto L0388;

		L0336:
			uiCityNameID = this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x8));
			AppendCityNameToReplayMessage(uiCityNameID);

			// Instruction address 0x0000:0x036b, size: 5
			this.oParent.CAPI.strcat(
				0xba06,
				ClassicGameText.Current[
					ClassicGameTextKey.ReplayCityDestroyedSuffix]);

			F9_0000_08a3();

			F9_0000_0a22(
				0xffff,
				this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xa)),
				this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xc)));

		L0388:
			F9_0000_0ac8(
				this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xa)),
				this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xc)));

			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.DS.UInt16, 0x680a), 0x1);
			if (this.oCPU.Flags.E) goto L039f;
			goto L0826;

		L039f:
			// Instruction address 0x0000:0x03a3, size: 5
			this.oParent.CommonTools.WaitTimer(30);

			goto L0826;

		L03ae:
			this.oCPU.AX.LowUInt8 = this.oParent.GameData.ReplayData[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))];
			this.oCPU.AX.HighUInt8 = 0;
			this.oCPU.CX.LowUInt8 = 0x4;
			this.oCPU.AX.UInt16 = this.oCPU.SHR_UInt16(this.oCPU.AX.UInt16, this.oCPU.CX.LowUInt8);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xa), this.oCPU.AX.UInt16);

			this.oCPU.AX.LowUInt8 = this.oParent.GameData.ReplayData[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))];
			this.oCPU.AX.HighUInt8 = 0;
			this.oCPU.AX.UInt16 = this.oCPU.AND_UInt16(this.oCPU.AX.UInt16, 0xf);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xc), this.oCPU.AX.UInt16);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2),
				this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))));

			// Instruction address 0x0000:0x03e0, size: 5
			this.oParent.CAPI.strcat(0xba06,
				GetLocalizedNation(
					this.oCPU.ReadInt16(
						this.oCPU.SS.UInt16,
						(ushort)(this.oCPU.BP.UInt16 - 0xa))));

			// Instruction address 0x0000:0x03f0, size: 5
			this.oParent.CAPI.strcat(
				0xba06,
				ClassicGameText.Current[
					ClassicGameTextKey.ReplayDeclareWarConnector]);

		L03eb:
			// Instruction address 0x0000:0x0405, size: 5
			this.oParent.CAPI.strcat(0xba06,
				GetLocalizedNation(
					this.oCPU.ReadInt16(
						this.oCPU.SS.UInt16,
						(ushort)(this.oCPU.BP.UInt16 - 0xc))));

		L040d:
			F9_0000_08a3();

			goto L0826;

		L0414:
			this.oCPU.AX.LowUInt8 = this.oParent.GameData.ReplayData[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))];
			this.oCPU.AX.HighUInt8 = 0;
			this.oCPU.CX.LowUInt8 = 0x4;
			this.oCPU.AX.UInt16 = this.oCPU.SHR_UInt16(this.oCPU.AX.UInt16, this.oCPU.CX.LowUInt8);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xa), this.oCPU.AX.UInt16);

			this.oCPU.AX.LowUInt8 = this.oParent.GameData.ReplayData[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))];
			this.oCPU.AX.HighUInt8 = 0;
			this.oCPU.AX.UInt16 = this.oCPU.AND_UInt16(this.oCPU.AX.UInt16, 0xf);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xc), this.oCPU.AX.UInt16);

			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2),
				this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))));

			// Instruction address 0x0000:0x0446, size: 5
			this.oParent.CAPI.strcat(
				0xba06,
				GetLocalizedNation(
					this.oCPU.ReadInt16(
						this.oCPU.SS.UInt16,
						(ushort)(this.oCPU.BP.UInt16 - 0xa))));

			// Instruction address 0x0000:0x03f0, size: 5
			this.oParent.CAPI.strcat(
				0xba06,
				ClassicGameText.Current[
					ClassicGameTextKey.ReplayMakePeaceConnector]);

			goto L03eb;

		L0453:
			this.oCPU.AX.LowUInt8 = this.oParent.GameData.ReplayData[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))];
			this.oCPU.AX.HighUInt8 = 0;
			this.oCPU.WriteUInt16(this.oCPU.DS.UInt16, 0x6810, this.oCPU.AX.UInt16);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2),
				this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))));

			this.oCPU.AX.LowUInt8 = this.oParent.GameData.ReplayData[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))];
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xc), this.oCPU.AX.UInt16);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2),
				this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))));

			// Instruction address 0x0000:0x0483, size: 5
			this.oParent.CAPI.strcat(
				0xba06,
				GetLocalizedNation(
					this.oCPU.ReadInt16(
						this.oCPU.DS.UInt16,
						0x6810)));

			// Instruction address 0x0000:0x0493, size: 5
			this.oParent.CAPI.strcat(
				0xba06,
				ClassicGameText.Current[
					ClassicGameTextKey.ReplayDiscoverConnector]);

			this.oParent.CAPI.strcat(0xba06, 
				this.oParent.GameData.TechnologyAdvances[this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xc))].Name);

			goto L040d;

		L04a8:
			this.oCPU.AX.LowUInt8 = this.oParent.GameData.ReplayData[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))];
			this.oCPU.AX.HighUInt8 = 0;
			this.oCPU.WriteUInt16(this.oCPU.DS.UInt16, 0x6810, this.oCPU.AX.UInt16);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2),
				this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))));

			this.oCPU.AX.LowUInt8 = this.oParent.GameData.ReplayData[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))];
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xc), this.oCPU.AX.UInt16);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2),
				this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))));

			// Instruction address 0x0000:0x04d8, size: 5
			this.oParent.CAPI.strcat(
				0xba06,
				GetLocalizedNation(
					this.oCPU.ReadInt16(
						this.oCPU.DS.UInt16,
						0x6810)));

			// Instruction address 0x0000:0x04e8, size: 5
			this.oParent.CAPI.strcat(
				0xba06,
				ClassicGameText.Current[
					ClassicGameTextKey.ReplayProduceFirstConnector]);

			// Instruction address 0x0000:0x0405, size: 5
			this.oParent.CAPI.strcat(
				0xba06,
				ClassicDisplayNames.Unit(
					(UnitTypeEnum)this.oCPU.ReadInt16(
						this.oCPU.SS.UInt16,
						(ushort)(this.oCPU.BP.UInt16 - 0xc)),
					this.oParent.GameData.Units[
						this.oCPU.ReadInt16(
							this.oCPU.SS.UInt16,
							(ushort)(this.oCPU.BP.UInt16 - 0xc))].Name));

			goto L040d;

		L04fb:
			this.oCPU.AX.LowUInt8 = this.oParent.GameData.ReplayData[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))];
			this.oCPU.AX.HighUInt8 = 0;
			this.oCPU.WriteUInt16(this.oCPU.DS.UInt16, 0x6810, this.oCPU.AX.UInt16);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2),
				this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))));

			this.oCPU.AX.LowUInt8 = this.oParent.GameData.ReplayData[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))];
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xc), this.oCPU.AX.UInt16);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2),
				this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))));

			// Instruction address 0x0000:0x052b, size: 5
			this.oParent.CAPI.strcat(
				0xba06,
				GetLocalizedNation(
					this.oCPU.ReadInt16(
						this.oCPU.DS.UInt16,
						0x6810)));

			// Instruction address 0x0000:0x053b, size: 5
			this.oParent.CAPI.strcat(
				0xba06,
				ClassicGameText.Current[
					ClassicGameTextKey.ReplayFormConnector]);

			// Instruction address 0x0000:0x0405, size: 5
			this.oParent.CAPI.strcat(
				0xba06,
				GetLocalizedGovernment(
					this.oCPU.ReadUInt16(
						this.oCPU.SS.UInt16,
						(ushort)(this.oCPU.BP.UInt16 - 0xc))));
			goto L040d;

		L054f:
			this.oCPU.AX.LowUInt8 = this.oParent.GameData.ReplayData[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))];
			this.oCPU.AX.HighUInt8 = 0;
			this.oCPU.WriteUInt16(this.oCPU.DS.UInt16, 0x6810, this.oCPU.AX.UInt16);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2),
				this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))));

			this.oCPU.AX.LowUInt8 = this.oParent.GameData.ReplayData[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))];
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xc), this.oCPU.AX.UInt16);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2),
				this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))));

			// Instruction address 0x0000:0x057f, size: 5
			this.oParent.CAPI.strcat(
				0xba06,
				GetLocalizedNation(
					this.oCPU.ReadInt16(
						this.oCPU.DS.UInt16,
						0x6810)));

			// Instruction address 0x0000:0x058f, size: 5
			this.oParent.CAPI.strcat(
				0xba06,
				ClassicGameText.Current[
					this.oCPU.ReadUInt16(
						this.oCPU.SS.UInt16,
						(ushort)(this.oCPU.BP.UInt16 - 0xc)) <= 7
							? ClassicGameTextKey
								.ReplayBuildAncientWonderConnector
							: ClassicGameTextKey
								.ReplayBuildWonderConnector]);

			// Instruction address 0x0000:0x0405, size: 5
			this.oParent.CAPI.strcat(0xba06,
				ClassicDisplayNames.Wonder(
					(WonderEnum)this.oCPU.ReadInt16(
						this.oCPU.SS.UInt16,
						(ushort)(this.oCPU.BP.UInt16 - 0xc)),
					this.oParent.GameData.Wonders[
						this.oCPU.ReadInt16(
							this.oCPU.SS.UInt16,
							(ushort)(this.oCPU.BP.UInt16 - 0xc))].Name));

			goto L040d;

		L05b9:
			this.oCPU.AX.UInt16 = (ushort)this.oParent.GameData.HumanPlayerID;
			this.oCPU.WriteUInt16(this.oCPU.DS.UInt16, 0x6810, this.oCPU.AX.UInt16);

			this.oCPU.AX.LowUInt8 = this.oParent.GameData.ReplayData[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))];
			this.oCPU.AX.HighUInt8 = 0;
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xa), this.oCPU.AX.UInt16);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2),
				this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))));

			this.oCPU.AX.LowUInt8 = this.oParent.GameData.ReplayData[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))];
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xc), this.oCPU.AX.UInt16);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2),
				this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))));

			this.oCPU.AX.LowUInt8 = this.oParent.GameData.ReplayData[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))];
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x10), this.oCPU.AX.UInt16);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2),
				this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))));

			// Instruction address 0x0000:0x05fd, size: 5
			this.oParent.CAPI.strcat(
				0xba06,
				GetLocalizedNation(
					this.oParent.GameData.HumanPlayerID));

			// Instruction address 0x0000:0x060d, size: 5
			this.oParent.CAPI.strcat(0xba06, ": ");

			// Instruction address 0x0000:0x062d, size: 5
			this.oParent.CAPI.strcat(0xba06,
				this.oParent.CAPI.itoa((short)this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xa)), 10));

			// Instruction address 0x0000:0x063d, size: 5
			this.oParent.CAPI.strcat(
				0xba06,
				ClassicGameText.Current[
					ClassicGameTextKey.ReplayEmpireCitiesConnector]);

			// Instruction address 0x0000:0x064e, size: 5
			this.oParent.CAPI.strcat(0xba06, this.oParent.Tools.F0_2dc4_0337_PopulationValueToString(
				this.oCPU.ReadInt8(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xc)) + this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x10))));

			// Instruction address 0x0000:0x0405, size: 5
			this.oParent.CAPI.strcat(
				0xba06,
				ClassicGameText.Current[
					ClassicGameTextKey.ReplayEmpirePopulationSuffix]);

			goto L040d;

		L065c:
			// Instruction address 0x0000:0x0664, size: 5
			this.oParent.CAPI.strcpy(0xba06, "*** ");

			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xa), 0x0);

		L0671:
			this.oCPU.TEST_UInt8(this.oParent.GameData.ReplayData[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))], 0xf0);
			if (this.oCPU.Flags.E) goto L06e8;

			// Instruction address 0x0000:0x069c, size: 5
			this.oParent.CAPI.strcat(0xba06,
				this.oParent.CAPI.itoa((short)((short)(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xa)) << 1) + 1), 10));

			// Instruction address 0x0000:0x06ac, size: 5
			this.oParent.CAPI.strcat(0xba06, ":");

			// Instruction address 0x0000:0x06d0, size: 5
			this.oParent.CAPI.strcat(0xba06,
				GetLocalizedNation(
					this.oParent.GameData.ReplayData[
						this.oCPU.ReadUInt16(
							this.oCPU.SS.UInt16,
							(ushort)(this.oCPU.BP.UInt16 - 0x2))] >> 4));

			// Instruction address 0x0000:0x06e0, size: 5
			this.oParent.CAPI.strcat(0xba06, " ");

		L06e8:
			this.oCPU.TEST_UInt8(this.oParent.GameData.ReplayData[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))], 0xf);
			if (this.oCPU.Flags.E) goto L075d;

			// Instruction address 0x0000:0x0714, size: 5
			this.oParent.CAPI.strcat(0xba06,
				this.oParent.CAPI.itoa((short)((short)(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xa)) << 1) + 2), 10));

			// Instruction address 0x0000:0x0724, size: 5
			this.oParent.CAPI.strcat(0xba06, ":");

			// Instruction address 0x0000:0x0745, size: 5
			this.oParent.CAPI.strcat(0xba06,
				GetLocalizedNation(
					this.oParent.GameData.ReplayData[
						this.oCPU.ReadUInt16(
							this.oCPU.SS.UInt16,
							(ushort)(this.oCPU.BP.UInt16 - 0x2))] & 0xf));

			// Instruction address 0x0000:0x0755, size: 5
			this.oParent.CAPI.strcat(0xba06, " ");

		L075d:
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2), 
				this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))));
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xa), 
				this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xa))));
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xa)), 0x4);
			if (this.oCPU.Flags.GE) goto L076c;
			goto L0671;

		L076c:
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.DS.UInt16, 0x680a), 0x3);
			if (this.oCPU.Flags.E) goto L0776;
			goto L0826;

		L0776:
			goto L040d;

		L0779:
			this.oCPU.AX.LowUInt8 = this.oParent.GameData.ReplayData[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))];
			this.oCPU.AX.HighUInt8 = 0;
			this.oCPU.WriteUInt16(this.oCPU.DS.UInt16, 0x6810, this.oCPU.AX.UInt16);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2),
				this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))));

			this.oCPU.AX.LowUInt8 = this.oParent.GameData.ReplayData[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))];
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xa), this.oCPU.AX.UInt16);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2),
				this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))));

			// Instruction address 0x0000:0x07a9, size: 5
			this.oParent.CAPI.strcat(
				0xba06,
				ClassicGameText.Current.Format(
					ClassicGameTextKey.ReplayCivilizationDestroyed,
					GetLocalizedNation(
						this.oCPU.ReadInt16(
							this.oCPU.DS.UInt16,
							0x6810),
						useNationality: true),
					GetLocalizedNation(
						this.oCPU.ReadInt16(
							this.oCPU.SS.UInt16,
							(ushort)(this.oCPU.BP.UInt16 - 0xa)))));

			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.DS.UInt16, 0x680a), 0x4);
			if (this.oCPU.Flags.NE) goto L07f3;
			this.oCPU.AX.UInt16 = (ushort)this.oParent.GameData.HumanPlayerID;
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xa)), this.oCPU.AX.UInt16);
			if (this.oCPU.Flags.NE) goto L07f3;

			F9_0000_0f79(this.oCPU.ReadInt16(this.oCPU.DS.UInt16, 0x6810),
				this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x4)));

		L07f3:
			this.oParent.GameData.Players[this.oCPU.ReadUInt16(this.oCPU.DS.UInt16, 0x6810)].NationalityID ^= 8;

			F9_0000_0d5d(this.oCPU.ReadInt16(this.oCPU.DS.UInt16, 0x6810));
			
			goto L040d;

		L0826:
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.DS.UInt16, 0x680a), 0x2);
			if (this.oCPU.Flags.E) goto L0830;
			goto L0196;

		L0830:
			// Instruction address 0x0000:0x0830, size: 5
			this.oParent.CAPI.getch();

			this.oCPU.CMP_UInt16(this.oCPU.AX.UInt16, 0x1b);
			if (this.oCPU.Flags.E) goto L083d;
			goto L0196;

		L083d:
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe), 0x1);

		L0842:
			this.oCPU.SI.UInt16 = this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe));
			this.oCPU.SI.UInt16 = this.oCPU.SHL_UInt16(this.oCPU.SI.UInt16, 0x1);
			this.oCPU.AX.UInt16 = this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 + this.oCPU.SI.UInt16 - 0x20));
			this.oParent.GameData.Players[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe))].NationalityID = (short)this.oCPU.AX.UInt16;

			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe), this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe))));
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe)), 0x8);
			if (this.oCPU.Flags.L) goto L0842;
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe), 0x1);

		L085c:
			this.oCPU.AX.UInt16 = (ushort)this.oParent.GameData.HumanPlayerID;
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe)), this.oCPU.AX.UInt16);
			if (this.oCPU.Flags.E) goto L086e;

			int restoredPlayerID =
				this.oCPU.ReadInt16(
					this.oCPU.SS.UInt16,
					(ushort)(this.oCPU.BP.UInt16 - 0xe));
			this.oParent.GameData.Players[restoredPlayerID].Nation =
				originalPlayerNations[restoredPlayerID];
			this.oParent.GameData.Players[restoredPlayerID].Nationality =
				originalPlayerNationalities[restoredPlayerID];

		L086e:
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe), 
				this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe))));
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xe)), 0x8);
			if (this.oCPU.Flags.L) goto L085c;

			this.oParent.Graphics.F0_VGA_07d8_DrawImage(this.oParent.Var_19d4_Screen1_Rectangle, 0, 0, 320, 200, this.oParent.Var_aa_Screen0_Rectangle, 0, 0);

			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.DS.UInt16, 0x680a), 0x3);
			if (this.oCPU.Flags.NE) goto L0894;
			
			// Instruction address 0x0000:0x088c, size: 5
			this.oParent.CAPI.close((short)this.oCPU.ReadUInt16(this.oCPU.DS.UInt16, 0x680c));

		L0894:
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.DS.UInt16, 0x680a), 0x3);
			if (this.oCPU.Flags.GE) goto L089e;
			goto L0007;

		L089e:
			this.oCPU.SI.UInt16 = this.oCPU.POP_UInt16();
			this.oCPU.SP.UInt16 = this.oCPU.BP.UInt16;
			this.oCPU.BP.UInt16 = this.oCPU.POP_UInt16();
			// Far return
			this.oCPU.Log.ExitBlock("F9_0000_0000");
		}

		/// <summary>
		/// ?
		/// </summary>
		public void F9_0000_08a3()
		{
			this.oCPU.Log.EnterBlock("F9_0000_08a3()");

			// function body
			this.oCPU.PUSH_UInt16(this.oCPU.BP.UInt16);
			this.oCPU.BP.UInt16 = this.oCPU.SP.UInt16;
			this.oCPU.SP.UInt16 = this.oCPU.SUB_UInt16(this.oCPU.SP.UInt16, 0x2);
			this.oParent.ReplayMessageShownForTests?.Invoke(
				this.oCPU.ReadString(this.oCPU.DS.UInt16, 0xba06));
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.DS.UInt16, 0x680a), 0x4);
			if (this.oCPU.Flags.NE) goto L08b3;
			goto L0978;

		L08b3:
			this.oCPU.AX.UInt16 = (ushort)this.oParent.GameData.HumanPlayerID;
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.DS.UInt16, 0x6810), this.oCPU.AX.UInt16);
			if (this.oCPU.Flags.NE) goto L08c8;

			// Instruction address 0x0000:0x08c0, size: 5
			this.oParent.CAPI.strupr(0xba06);

		L08c8:
			// Instruction address 0x0000:0x08dc, size: 5
			this.oParent.DrawTools.FillRectangle(this.oParent.Var_aa_Screen0_Rectangle, 0, 0, 320, 8, 15);

			// Instruction address 0x0000:0x08f3, size: 5
			this.oParent.DrawTools.F0_1182_005c_DrawStringToScreen0(0xba06, 4, 1, 0);

			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.DS.UInt16, 0x680a), 0x3);
			if (this.oCPU.Flags.NE) goto L0935;

			// Instruction address 0x0000:0x0906, size: 5
			this.oParent.CAPI.strlen(0xba06);

			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2), this.oCPU.AX.UInt16);
			this.oCPU.BX.UInt16 = this.oCPU.AX.UInt16;
			this.oCPU.WriteUInt8(this.oCPU.DS.UInt16, (ushort)(this.oCPU.BX.UInt16 + 0xba06), 0xd);
			this.oCPU.WriteUInt8(this.oCPU.DS.UInt16, (ushort)(this.oCPU.BX.UInt16 + 0xba07), 0xa);
			this.oCPU.WriteUInt8(this.oCPU.DS.UInt16, (ushort)(this.oCPU.BX.UInt16 + 0xba08), 0x0);
			this.oCPU.AX.UInt16 = this.oCPU.INC_UInt16(this.oCPU.AX.UInt16);
			this.oCPU.AX.UInt16 = this.oCPU.INC_UInt16(this.oCPU.AX.UInt16);

			// Instruction address 0x0000:0x092d, size: 5
			this.oParent.CAPI.write((short)this.oCPU.ReadUInt16(this.oCPU.DS.UInt16, 0x680c), 0xba06, this.oCPU.AX.UInt16);

		L0935:
			// Instruction address 0x0000:0x093d, size: 5
			this.oParent.CAPI.strcpy(0xba06, this.oParent.LanguageTools.F0_2f4d_04f7_TrimStringToWidth(this.oCPU.ReadString(this.oCPU.DS.UInt16, 0xba06), 312));

			// Instruction address 0x0000:0x0959, size: 5
			this.oParent.DrawTools.FillRectangle(this.oParent.Var_aa_Screen0_Rectangle, 0, 0, 320, 8, 15);

			// Instruction address 0x0000:0x0970, size: 5
			this.oParent.DrawTools.F0_1182_005c_DrawStringToScreen0(0xba06, 4, 1, 0);

		L0978:
			this.oCPU.SP.UInt16 = this.oCPU.BP.UInt16;
			this.oCPU.BP.UInt16 = this.oCPU.POP_UInt16();
			// Far return
			this.oCPU.Log.ExitBlock("F9_0000_08a3");
		}

		/// <summary>
		/// ?
		/// </summary>
		/// <param name="param1"></param>
		/// <param name="param2"></param>
		/// <param name="param3"></param>
		public void F9_0000_09dc(ushort param1, ushort param2, ushort param3)
		{
			this.oCPU.Log.EnterBlock($"F9_0000_09dc({param1}, {param2}, {param3})");

			// function body
			this.oCPU.PUSH_UInt16(this.oCPU.BP.UInt16);
			this.oCPU.BP.UInt16 = this.oCPU.SP.UInt16;
			this.oCPU.SP.UInt16 = this.oCPU.SUB_UInt16(this.oCPU.SP.UInt16, 0x2);
			this.oCPU.PUSH_UInt16(this.oCPU.SI.UInt16);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2), 0x0);
			goto L09ed;

		L09ea:
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2),
				this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))));

		L09ed:
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2)), 0x80);
			if (this.oCPU.Flags.GE) goto L0a1d;

			this.oCPU.SI.UInt16 = this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2));
			this.oCPU.SI.UInt16 = this.oCPU.SHL_UInt16(this.oCPU.SI.UInt16, 0x1);
			this.oCPU.ES.UInt16 = 0x3725; // segment
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.ES.UInt16, (ushort)(this.oCPU.SI.UInt16 + 0x0)), 0xffff);
			if (this.oCPU.Flags.NE) goto L09ea;

			this.oCPU.WriteUInt16(this.oCPU.ES.UInt16, (ushort)(this.oCPU.SI.UInt16 + 0x0), param1);
			this.oCPU.WriteUInt16(this.oCPU.ES.UInt16, (ushort)(this.oCPU.SI.UInt16 + 0x100), param2);
			this.oCPU.WriteUInt16(this.oCPU.ES.UInt16, (ushort)(this.oCPU.SI.UInt16 + 0x200), param3);

		L0a1d:
			this.oCPU.SI.UInt16 = this.oCPU.POP_UInt16();
			this.oCPU.SP.UInt16 = this.oCPU.BP.UInt16;
			this.oCPU.BP.UInt16 = this.oCPU.POP_UInt16();
			// Far return
			this.oCPU.Log.ExitBlock("F9_0000_09dc");
		}

		/// <summary>
		/// ?
		/// </summary>
		/// <param name="param1"></param>
		/// <param name="param2"></param>
		/// <param name="param3"></param>
		public void F9_0000_0a22(ushort param1, ushort param2, ushort param3)
		{
			this.oCPU.Log.EnterBlock($"F9_0000_0a22({param1}, {param2}, {param3})");

			// function body
			this.oCPU.PUSH_UInt16(this.oCPU.BP.UInt16);
			this.oCPU.BP.UInt16 = this.oCPU.SP.UInt16;
			this.oCPU.SP.UInt16 = this.oCPU.SUB_UInt16(this.oCPU.SP.UInt16, 0x2);
			this.oCPU.PUSH_UInt16(this.oCPU.SI.UInt16);

			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2), 0x0);
			goto L0a33;

		L0a30:
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2),
				this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))));

		L0a33:
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2)), 0x80);
			if (this.oCPU.Flags.GE) goto L0a5f;

			this.oCPU.SI.UInt16 = this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2));
			this.oCPU.SI.UInt16 = this.oCPU.SHL_UInt16(this.oCPU.SI.UInt16, 0x1);
			this.oCPU.ES.UInt16 = 0x3725; // segment
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.ES.UInt16, (ushort)(this.oCPU.SI.UInt16 + 0x100)), param2);
			if (this.oCPU.Flags.NE) goto L0a30;

			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.ES.UInt16, (ushort)(this.oCPU.SI.UInt16 + 0x200)), param3);
			if (this.oCPU.Flags.NE) goto L0a30;

			this.oCPU.WriteUInt16(this.oCPU.ES.UInt16, (ushort)(this.oCPU.SI.UInt16 + 0x0), param1);

		L0a5f:
			this.oCPU.SI.UInt16 = this.oCPU.POP_UInt16();
			this.oCPU.SP.UInt16 = this.oCPU.BP.UInt16;
			this.oCPU.BP.UInt16 = this.oCPU.POP_UInt16();
			// Far return
			this.oCPU.Log.ExitBlock("F9_0000_0a22");
		}

		/// <summary>
		/// ?
		/// </summary>
		/// <param name="xPos"></param>
		/// <param name="yPos"></param>
		/// <returns></returns>
		public ushort F9_0000_0a64(int xPos, int yPos)
		{
			this.oCPU.Log.EnterBlock($"F9_0000_0a64({xPos}, {yPos})");

			// function body
			this.oCPU.PUSH_UInt16(this.oCPU.BP.UInt16);
			this.oCPU.BP.UInt16 = this.oCPU.SP.UInt16;
			this.oCPU.SP.UInt16 = this.oCPU.SUB_UInt16(this.oCPU.SP.UInt16, 0x6);
			this.oCPU.PUSH_UInt16(this.oCPU.SI.UInt16);

			this.oCPU.WriteUInt16(this.oCPU.DS.UInt16, 0x6812, 0x3e7);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x6), 0x0);

		L0a76:
			this.oCPU.SI.UInt16 = this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x6));
			this.oCPU.SI.UInt16 = this.oCPU.SHL_UInt16(this.oCPU.SI.UInt16, 0x1);
			this.oCPU.ES.UInt16 = 0x3725; // segment
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.ES.UInt16, (ushort)(this.oCPU.SI.UInt16 + 0x0)), 0xffff);
			if (this.oCPU.Flags.E) goto L0ab6;

			// Instruction address 0x0000:0x0a97, size: 5
			this.oCPU.AX.Int16 = (short)this.oParent.Tools.F0_2dc4_0289_GetShortestDistance(
				xPos, yPos,
				this.oCPU.ReadInt16(this.oCPU.ES.UInt16, (ushort)(this.oCPU.SI.UInt16 + 0x100)), this.oCPU.ReadInt16(this.oCPU.ES.UInt16, (ushort)(this.oCPU.SI.UInt16 + 0x200)));

			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2), this.oCPU.AX.UInt16);
			this.oCPU.AX.UInt16 = this.oCPU.ReadUInt16(this.oCPU.DS.UInt16, 0x6812);
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2)), this.oCPU.AX.UInt16);
			if (this.oCPU.Flags.GE) goto L0ab6;
			this.oCPU.AX.UInt16 = this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2));
			this.oCPU.WriteUInt16(this.oCPU.DS.UInt16, 0x6812, this.oCPU.AX.UInt16);
			this.oCPU.AX.UInt16 = this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x6));
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x4), this.oCPU.AX.UInt16);

		L0ab6:
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x6), this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x6))));
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x6)), 0x80);
			if (this.oCPU.Flags.L) goto L0a76;

			this.oCPU.AX.UInt16 = this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x4));

			this.oCPU.SI.UInt16 = this.oCPU.POP_UInt16();
			this.oCPU.SP.UInt16 = this.oCPU.BP.UInt16;
			this.oCPU.BP.UInt16 = this.oCPU.POP_UInt16();

			// Far return
			this.oCPU.Log.ExitBlock("F9_0000_0a64");

			return this.oCPU.AX.UInt16;
		}

		/// <summary>
		/// ?
		/// </summary>
		/// <param name="xPos"></param>
		/// <param name="yPos"></param>
		public void F9_0000_0ac8(int xPos, int yPos)
		{
			this.oCPU.Log.EnterBlock($"F9_0000_0ac8({xPos}, {yPos})");

			// function body
			this.oCPU.PUSH_UInt16(this.oCPU.BP.UInt16);
			this.oCPU.BP.UInt16 = this.oCPU.SP.UInt16;
			this.oCPU.SP.UInt16 = this.oCPU.SUB_UInt16(this.oCPU.SP.UInt16, 0xc);
			this.oCPU.PUSH_UInt16(this.oCPU.DI.UInt16);
			this.oCPU.PUSH_UInt16(this.oCPU.SI.UInt16);
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.DS.UInt16, 0x680a), 0x4);
			if (this.oCPU.Flags.NE) goto L0ada;
			goto L0c2a;

		L0ada:
			// Instruction address 0x0000:0x0ae8, size: 5
			this.oCPU.AX.Int16 = (short)this.oParent.Tools.F0_2dc4_007c_CheckValueRange(xPos - 5, 0, 80);

			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2), this.oCPU.AX.UInt16);

			// Instruction address 0x0000:0x0b01, size: 5
			this.oCPU.AX.Int16 = (short)this.oParent.Tools.F0_2dc4_007c_CheckValueRange(xPos + 5, 0, 80);

			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x6), this.oCPU.AX.UInt16);

			// Instruction address 0x0000:0x0b1b, size: 5
			this.oCPU.AX.Int16 = (short)this.oParent.Tools.F0_2dc4_007c_CheckValueRange(yPos - 5, 2, 49);

			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x8), this.oCPU.AX.UInt16);

			// Instruction address 0x0000:0x0b35, size: 5
			this.oCPU.AX.Int16 = (short)this.oParent.Tools.F0_2dc4_007c_CheckValueRange(yPos + 5, 2, 49);

			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xa), this.oCPU.AX.UInt16);

			yPos = this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x8));

			goto L0c19;

		L0b49:
			this.oCPU.BX.UInt16 = this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x4));
			this.oCPU.BX.UInt16 = this.oCPU.SHL_UInt16(this.oCPU.BX.UInt16, 0x1);
			this.oCPU.ES.UInt16 = 0x3725; // segment
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.ES.UInt16, (ushort)(this.oCPU.BX.UInt16 + 0x0)), 0x1);
			if (this.oCPU.Flags.NE) goto L0b5f;

			// Instruction address 0x0000:0x0b84, size: 5
			this.oParent.DrawTools.FillRectangle(this.oParent.Var_aa_Screen0_Rectangle, xPos * 4, (yPos * 4) + 4, 4, 4, 7);
			goto L0b8c;

		L0b5f:
			// Instruction address 0x0000:0x0b84, size: 5
			this.oParent.DrawTools.FillRectangle(this.oParent.Var_aa_Screen0_Rectangle, xPos * 4, (yPos * 4) + 4, 4, 4, 15);
			goto L0b8c;

		L0b64:
			// Instruction address 0x0000:0x0b84, size: 5
			this.oParent.DrawTools.FillRectangle(this.oParent.Var_aa_Screen0_Rectangle, xPos * 4, (yPos * 4) + 4, 4, 4, 8);

		L0b8c:
			xPos++;

		L0b8f:
			if (xPos >= this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x6)))
				goto L0c16;

			// Instruction address 0x0000:0x0b9d, size: 5
			this.oCPU.AX.Int16 = (short)this.oParent.MapManagement.GetTerrainType(xPos, yPos);

			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xc), this.oCPU.AX.UInt16);
			this.oCPU.CMP_UInt16(this.oCPU.AX.UInt16, 0xa);
			if (this.oCPU.Flags.E) goto L0b8c;

			F9_0000_0a64(xPos, yPos);

			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x4), this.oCPU.AX.UInt16);
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.DS.UInt16, 0x6812), 0x6);
			if (this.oCPU.Flags.GE) goto L0b64;
			this.oCPU.SI.UInt16 = this.oCPU.AX.UInt16;
			this.oCPU.SI.UInt16 = this.oCPU.SHL_UInt16(this.oCPU.SI.UInt16, 0x1);
			this.oCPU.ES.UInt16 = 0x3725; // segment

			// Instruction address 0x0000:0x0bd6, size: 5
			this.oCPU.AX.Int16 = (short)this.oParent.MapManagement.F0_2aea_1942_GetGroupID(
				this.oCPU.ReadInt16(this.oCPU.ES.UInt16, (ushort)(this.oCPU.SI.UInt16 + 0x100)),
				this.oCPU.ReadInt16(this.oCPU.ES.UInt16, (ushort)(this.oCPU.SI.UInt16 + 0x200)));

			this.oCPU.DI.UInt16 = this.oCPU.AX.UInt16;

			// Instruction address 0x0000:0x0be6, size: 5
			this.oCPU.AX.Int16 = (short)this.oParent.MapManagement.F0_2aea_1942_GetGroupID(xPos, yPos);

			this.oCPU.CMP_UInt16(this.oCPU.AX.UInt16, this.oCPU.DI.UInt16);
			if (this.oCPU.Flags.E) goto L0bf5;
			goto L0b64;

		L0bf5:
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.DS.UInt16, 0x6812), 0x0);
			if (this.oCPU.Flags.NE) goto L0bff;
			goto L0b49;

		L0bff:
			this.oCPU.BX.UInt16 = this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x4));
			this.oCPU.BX.UInt16 = this.oCPU.SHL_UInt16(this.oCPU.BX.UInt16, 0x1);
			this.oCPU.ES.UInt16 = 0x3725; // segment
			this.oCPU.BX.UInt16 = this.oCPU.ReadUInt16(this.oCPU.ES.UInt16, (ushort)(this.oCPU.BX.UInt16 + 0x0));
			// Instruction address 0x0000:0x0b84, size: 5
			this.oParent.DrawTools.FillRectangle(this.oParent.Var_aa_Screen0_Rectangle, xPos * 4, (yPos * 4) + 4, 4, 4,
				this.oParent.Array_1946_PlayerColours[this.oCPU.BX.UInt16]);
			goto L0b8c;

		L0c16:
			yPos++;

		L0c19:
			if (yPos >= this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xa)))
				goto L0c2a;

			xPos = this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2));
			goto L0b8f;

		L0c2a:
			this.oCPU.SI.UInt16 = this.oCPU.POP_UInt16();
			this.oCPU.DI.UInt16 = this.oCPU.POP_UInt16();
			this.oCPU.SP.UInt16 = this.oCPU.BP.UInt16;
			this.oCPU.BP.UInt16 = this.oCPU.POP_UInt16();
			// Far return
			this.oCPU.Log.ExitBlock("F9_0000_0ac8");
		}

		/// <summary>
		/// ?
		/// </summary>
		public void F9_0000_0c30()
		{
			this.oCPU.Log.EnterBlock("F9_0000_0c30()");

			// function body
			this.oCPU.PUSH_UInt16(this.oCPU.BP.UInt16);
			this.oCPU.BP.UInt16 = this.oCPU.SP.UInt16;
			this.oCPU.SP.UInt16 = this.oCPU.SUB_UInt16(this.oCPU.SP.UInt16, 0x8);
			this.oCPU.PUSH_UInt16(this.oCPU.SI.UInt16);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x6), 0x0);
			goto L0d3b;

		L0c3f:
			this.oCPU.AX.LowUInt8 = 0x2e;

		L0c41:
			this.oCPU.BX.UInt16 = this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x4));
			this.oCPU.WriteUInt8(this.oCPU.DS.UInt16, (ushort)(this.oCPU.BX.UInt16 + 0xba06), this.oCPU.AX.LowUInt8);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x4), this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x4))));

		L0c4b:
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x4)), 0x50);
			if (this.oCPU.Flags.GE) goto L0c68;

			// Instruction address 0x0000:0x0c57, size: 5
			this.oCPU.AX.Int16 = (short)this.oParent.MapManagement.GetTerrainType(
				this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x4)),
				this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x6)));

			this.oCPU.CMP_UInt16(this.oCPU.AX.UInt16, 0xa);
			if (this.oCPU.Flags.NE) goto L0c3f;
			this.oCPU.AX.LowUInt8 = 0x20;
			goto L0c41;

		L0c68:
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x4), 0x0);
			goto L0cbf;

		L0c6f:
			this.oCPU.AX.LowUInt8 = 0x2b;

		L0c71:
			this.oCPU.BX.UInt16 = this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x4));
			this.oCPU.WriteUInt8(this.oCPU.DS.UInt16, (ushort)(this.oCPU.BX.UInt16 + 0xba06), this.oCPU.AX.LowUInt8);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2), 0x0);

		L0c7d:
			this.oCPU.AX.LowUInt8 = (byte)this.oParent.GameData.CityNames[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x8))][this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))];

			this.oCPU.SI.UInt16 = this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x4));
			this.oCPU.BX.UInt16 = this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2));
			this.oCPU.WriteUInt8(this.oCPU.DS.UInt16, (ushort)(this.oCPU.BX.UInt16 + this.oCPU.SI.UInt16 + 0xba07), this.oCPU.AX.LowUInt8);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2),
				this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))));
			this.oCPU.AX.UInt16 = this.oCPU.SI.UInt16;
			this.oCPU.AX.UInt16 = this.oCPU.ADD_UInt16(this.oCPU.AX.UInt16, this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2)));
			this.oCPU.AX.UInt16 = this.oCPU.INC_UInt16(this.oCPU.AX.UInt16);
			this.oCPU.CMP_UInt16(this.oCPU.AX.UInt16, 0x50);
			if (this.oCPU.Flags.GE) goto L0cbc;

			if (this.oParent.GameData.CityNames[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x8))][this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))] != '\0')
				goto L0c7d;

		L0cbc:
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x4), this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x4))));

		L0cbf:
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x4)), 0x50);
			if (this.oCPU.Flags.GE) goto L0d24;

			// Instruction address 0x0000:0x0ccb, size: 5
			this.oCPU.AX.Int16 = (short)this.oParent.MapManagement.GetTerrainType(
				this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x4)),
				this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x6)));

			this.oCPU.CMP_UInt16(this.oCPU.AX.UInt16, 0xa);
			if (this.oCPU.Flags.E) goto L0cbc;
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x8), 0x0);
			goto L0ce2;

		L0cdf:
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x8), 
				this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x8))));

		L0ce2:
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x8)), 0x100);
			if (this.oCPU.Flags.GE) goto L0cbc;
			this.oCPU.AX.LowUInt8 = (byte)((sbyte)this.oParent.GameData.CityPositions[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x8))].X);
			this.oCPU.CBW(this.oCPU.AX);
			this.oCPU.CMP_UInt16(this.oCPU.AX.UInt16, this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x4)));
			if (this.oCPU.Flags.NE) goto L0cdf;
			this.oCPU.AX.LowUInt8 = (byte)((sbyte)this.oParent.GameData.CityPositions[this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x8))].Y);
			this.oCPU.CBW(this.oCPU.AX);
			this.oCPU.CMP_UInt16(this.oCPU.AX.UInt16, this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x6)));
			if (this.oCPU.Flags.NE) goto L0cdf;

			// Instruction address 0x0000:0x0d10, size: 5
			this.oCPU.AX.Int16 = (short)this.oParent.MapManagement.F0_2aea_1585_GetVisibleTerrainImprovements(
				this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x4)),
				this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x6)));

			this.oCPU.TEST_UInt8(this.oCPU.AX.LowUInt8, 0x1);
			if (this.oCPU.Flags.NE) goto L0d1f;
			goto L0c6f;

		L0d1f:
			this.oCPU.AX.LowUInt8 = 0x2a;
			goto L0c71;

		L0d24:
			// Instruction address 0x0000:0x0d30, size: 5
			this.oParent.CAPI.write((short)this.oCPU.ReadUInt16(this.oCPU.DS.UInt16, 0x680c), 0xba06, 0x52);

			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x6), this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x6))));

		L0d3b:
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x6)), 0x32);
			if (this.oCPU.Flags.GE) goto L0d58;
			this.oCPU.WriteUInt8(this.oCPU.DS.UInt16, 0xba56, 0xd);
			this.oCPU.WriteUInt8(this.oCPU.DS.UInt16, 0xba57, 0xa);
			this.oCPU.WriteUInt8(this.oCPU.DS.UInt16, 0xba58, 0x0);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x4), 0x0);
			goto L0c4b;

		L0d58:
			this.oCPU.SI.UInt16 = this.oCPU.POP_UInt16();
			this.oCPU.SP.UInt16 = this.oCPU.BP.UInt16;
			this.oCPU.BP.UInt16 = this.oCPU.POP_UInt16();
			// Far return
			this.oCPU.Log.ExitBlock("F9_0000_0c30");
		}

		/// <summary>
		/// ?
		/// </summary>
		/// <param name="playerID"></param>
		public void F9_0000_0d5d(short playerID)
		{
			this.oCPU.Log.EnterBlock($"F9_0000_0d5d({playerID})");

			// function body
			this.oCPU.PUSH_UInt16(this.oCPU.BP.UInt16);
			this.oCPU.BP.UInt16 = this.oCPU.SP.UInt16;
			this.oCPU.SP.UInt16 = this.oCPU.SUB_UInt16(this.oCPU.SP.UInt16, 0x10);
			this.oCPU.PUSH_UInt16(this.oCPU.SI.UInt16);

			this.oCPU.SI.UInt16 = (ushort)playerID;
			this.oCPU.SI.UInt16 = this.oCPU.SHL_UInt16(this.oCPU.SI.UInt16, 0x1);

			// Instruction address 0x0000:0x0d78, size: 5
			this.oParent.GameData.Players[playerID].Nationality = 
				this.oParent.GameData.Nations[this.oParent.GameData.Players[playerID].NationalityID].Nationality;

			// Instruction address 0x0000:0x0d8f, size: 5
			this.oParent.CAPI.strcpy((ushort)(this.oCPU.BP.UInt16 - 0x10),
				this.oParent.GameData.Nations[this.oParent.GameData.Players[playerID].NationalityID].Nation);

			this.oCPU.CMP_UInt8(this.oCPU.ReadUInt8(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x10)), 0x0);
			if (this.oCPU.Flags.NE) goto L0dc4;

			// Instruction address 0x0000:0x0dac, size: 5
			this.oParent.CAPI.strcpy((ushort)(this.oCPU.BP.UInt16 - 0x10),
				this.oParent.GameData.Nations[this.oParent.GameData.Players[playerID].NationalityID].Nationality);

			// Instruction address 0x0000:0x0dbc, size: 5
			this.oParent.CAPI.strcat((ushort)(this.oCPU.BP.UInt16 - 0x10), "s");

		L0dc4:
			// Instruction address 0x0000:0x0dd1, size: 5
			this.oParent.GameData.Players[playerID].Nation = this.oCPU.ReadString(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x10));

			this.oCPU.SI.UInt16 = this.oCPU.POP_UInt16();
			this.oCPU.SP.UInt16 = this.oCPU.BP.UInt16;
			this.oCPU.BP.UInt16 = this.oCPU.POP_UInt16();
			// Far return
			this.oCPU.Log.ExitBlock("F9_0000_0d5d");
		}

		/// <summary>
		/// ?
		/// </summary>
		public void F9_0000_0dde()
		{
			this.oCPU.Log.EnterBlock("F9_0000_0dde()");

			// function body
			this.oCPU.PUSH_UInt16(this.oCPU.BP.UInt16);
			this.oCPU.BP.UInt16 = this.oCPU.SP.UInt16;
			this.oCPU.SP.UInt16 = this.oCPU.SUB_UInt16(this.oCPU.SP.UInt16, 0x2);
			this.oCPU.WriteUInt16(this.oCPU.DS.UInt16, 0x680e, 0x1);

			// Instruction address 0x0000:0x0dea, size: 5
			this.oParent.Tools.F0_2dc4_065f_StopPaletteCycleSlots();

			this.oCPU.WriteUInt8(this.oCPU.DS.UInt16, 0xb1d4, 0x0);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2), 0x0);

		L0dfe:
			this.oCPU.BX.UInt16 = this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2));
			this.oCPU.ES.UInt16 = 0x3772; // segment
			this.oCPU.WriteUInt8(this.oCPU.ES.UInt16, (ushort)(this.oCPU.BX.UInt16 + 0x37c4), 0xff);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2), this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2))));
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2)), 0xe);
			if (this.oCPU.Flags.L) goto L0dfe;

			// Instruction address 0x0000:0x0e27, size: 5
			this.oParent.DrawTools.FillRectangle(this.oParent.Var_aa_Screen0_Rectangle, 0, 0, 320, 200, 0);

			this.oParent.Var_aa_Screen0_Rectangle.FontID = 6;

			F9_0000_0000();

			// Instruction address 0x0000:0x0e53, size: 5
			this.oParent.CommonTools.PlayTune(
				this.oParent.GameData.Nations[this.oParent.GameData.Players[this.oParent.GameData.HumanPlayerID].NationalityID].LongTune, 3);

			// Instruction address 0x0000:0x0e7f, size: 5
			this.oParent.DrawTools.FillRectangle(this.oParent.Var_aa_Screen0_Rectangle, 18, 150, 284, 32, 34);

			// Instruction address 0x0000:0x0e8f, size: 5
			this.oParent.CAPI.strcpy(
				0xba06,
				ClassicGameText.Current[
					ClassicGameTextKey.ReplayWorldHails]);

			// Instruction address 0x0000:0x0ea7, size: 5
			this.oParent.DrawTools.F0_1182_00b3_DrawCenteredStringToScreen0(0xba06, 160, 152, 20);

			// Instruction address 0x0000:0x0ecb, size: 5
			this.oParent.DrawTools.F0_1182_00b3_DrawCenteredStringToScreen0(0xba06, 160, 151, 23);
			
			// Instruction address 0x0000:0x0ee1, size: 5
			this.oParent.CAPI.strcpy(
				0xba06,
				ClassicGameText.Current.Format(
					ClassicGameTextKey.ReplayConquerorLine,
					this.oParent.GameData.Players[
						this.oParent.GameData.HumanPlayerID].Name));

			// Instruction address 0x0000:0x0f09, size: 5
			this.oParent.DrawTools.F0_1182_00b3_DrawCenteredStringToScreen0(0xba06, 160, 168, 20);

			// Instruction address 0x0000:0x0f2d, size: 5
			this.oParent.DrawTools.F0_1182_00b3_DrawCenteredStringToScreen0(0xba06, 160, 167, 23);

			// Instruction address 0x0000:0x0f35, size: 5
			this.oParent.CommonTools.ClearKeyboardAndMouseEvents();

			// Instruction address 0x0000:0x0f3a, size: 5
			this.oParent.Segment_2459.F0_2459_0918_WaitForKeyPressOrMouseClick();

			// Instruction address 0x0000:0x0f43, size: 5
			this.oParent.CommonTools.PlayTune(1, 0);

			this.oParent.Var_aa_Screen0_Rectangle.FontID = 1;

			// Instruction address 0x0000:0x0f6a, size: 5
			this.oParent.Segment_1238.F0_1238_1b44();

			this.oCPU.WriteUInt16(this.oCPU.DS.UInt16, 0x680e, 0x0);
			this.oCPU.SP.UInt16 = this.oCPU.BP.UInt16;
			this.oCPU.BP.UInt16 = this.oCPU.POP_UInt16();
			// Far return
			this.oCPU.Log.ExitBlock("F9_0000_0dde");
		}

		/// <summary>
		/// ?
		/// </summary>
		/// <param name="playerID"></param>
		/// <param name="param2"></param>
		public void F9_0000_0f79(short playerID, ushort param2)
		{
			this.oCPU.Log.EnterBlock($"F9_0000_0f79({playerID}, {param2})");

			// function body
			this.oCPU.PUSH_UInt16(this.oCPU.BP.UInt16);
			this.oCPU.BP.UInt16 = this.oCPU.SP.UInt16;
			this.oCPU.SP.UInt16 = this.oCPU.SUB_UInt16(this.oCPU.SP.UInt16, 0x36);
			this.oCPU.PUSH_UInt16(this.oCPU.SI.UInt16);

			this.oCPU.BX.UInt16 = (ushort)this.oParent.GameData.Players[playerID].NationalityID;
			this.oCPU.AX.LowUInt8 = this.oCPU.ReadUInt8(this.oCPU.DS.UInt16, (ushort)(this.oCPU.BX.UInt16 + 0x3938));
			this.oCPU.CBW(this.oCPU.AX);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x32), this.oCPU.AX.UInt16);

			// Instruction address 0x0000:0x0f9e, size: 5
			this.oParent.CAPI.strcpy((ushort)(this.oCPU.BP.UInt16 - 0x10), "KING00.PIC");

			this.oCPU.AX.UInt16 = this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x32));
			this.oCPU.CWD(this.oCPU.AX, this.oCPU.DX);
			this.oCPU.CX.UInt16 = 0xa;
			this.oCPU.IDIV_UInt16(this.oCPU.AX, this.oCPU.DX, this.oCPU.CX.UInt16);
			this.oCPU.WriteUInt8(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xb), this.oCPU.ADD_UInt8(this.oCPU.ReadUInt8(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xb)), this.oCPU.DX.LowUInt8));
			this.oCPU.AX.UInt16 = this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x32));
			this.oCPU.CWD(this.oCPU.AX, this.oCPU.DX);
			this.oCPU.IDIV_UInt16(this.oCPU.AX, this.oCPU.DX, this.oCPU.CX.UInt16);
			this.oCPU.WriteUInt8(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xc), this.oCPU.ADD_UInt8(this.oCPU.ReadUInt8(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0xc)), this.oCPU.AX.LowUInt8));
			
			// Instruction address 0x0000:0x0ff5, size: 5
			this.oParent.ImageTools.F0_2fa1_01a2_LoadBitmapOrPalette(1, 0, 0, (ushort)(this.oCPU.BP.UInt16 - 0x10), 0);

			// Instruction address 0x0000:0x1011, size: 5
			this.oParent.Graphics.F0_VGA_0b85_ScreenToBitmap(1, 0xb5, 0x43, 0x8b, 0x85);

			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x12), this.oCPU.AX.UInt16);

			// Instruction address 0x0000:0x102d, size: 5
			this.oParent.Graphics.F0_VGA_0b85_ScreenToBitmap(1, 1, 0x33, 0x3b, 0x31);

			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x36), this.oCPU.AX.UInt16);

			// Instruction address 0x0000:0x1049, size: 5
			this.oParent.Graphics.F0_VGA_0b85_ScreenToBitmap(1,1,0x97,0x3b,0x31);

			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x30), this.oCPU.AX.UInt16);

			// Instruction address 0x0000:0x1061, size: 5
			this.oParent.ImageTools.F0_2fa1_01a2_LoadBitmapOrPalette(1, 0, 0, "SLAM1.PIC", 0);

			// Instruction address 0x0000:0x1079, size: 5
			this.oParent.CommonTools.TransformPaletteToColor(5, Color.FromRgb(0, 0, 0));

			// Instruction address 0x0000:0x1099, size: 5
			this.oParent.Graphics.F0_VGA_07d8_DrawImage(this.oParent.Var_19d4_Screen1_Rectangle, 0, 0, 320, 200, this.oParent.Var_aa_Screen0_Rectangle, 0, 0);

			// Instruction address 0x0000:0x10a9, size: 5
			this.oParent.CAPI.strcpy((ushort)(this.oCPU.BP.UInt16 - 0x24), "SLAM2.PIC");

			// Instruction address 0x0000:0x10ce, size: 5
			this.oParent.ImageTools.F0_2fa1_01a2_LoadBitmapOrPalette(1, 0, 133, (ushort)(this.oCPU.BP.UInt16 - 0x24), 0);

			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2e), 0x0);

		L10db:
			this.oCPU.BX.UInt16 = this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2e));
			this.oCPU.ES.UInt16 = 0x3772; // segment
			if (this.oCPU.ReadUInt8(this.oCPU.ES.UInt16, (ushort)(this.oCPU.BX.UInt16 + 0x37c4)) != 0xff)
			{
				this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2a),
					this.oCPU.ReadUInt8(this.oCPU.ES.UInt16, (ushort)(this.oCPU.BX.UInt16 + 0x37c4)));

				// Instruction address 0x0000:0x114d, size: 5
				this.oParent.Graphics.F0_VGA_07d8_DrawImage(this.oParent.Var_19d4_Screen1_Rectangle,
					((this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2a)) % 7) * 28) + 1,
					((this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2a)) / 7) * 34) + 133,
					27, 33,
					this.oParent.Var_aa_Screen0_Rectangle,
					((this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2e)) % 7) * 46) + 8,
					((-(this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2e)) / 7)) * 42) + 49);
			}

			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2e), this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2e))));
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2e)), 0xe);
			if (this.oCPU.Flags.GE) goto L1161;
			goto L10db;

		L1161:
			this.oCPU.AX.UInt16 = this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x32));
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x14), this.oCPU.AX.UInt16);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x28), 0x5a);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2c), 0x0);
			this.oCPU.SI.UInt16 = this.oCPU.AX.UInt16;
			this.oCPU.CX.LowUInt8 = 0x2;
			this.oCPU.SI.UInt16 = this.oCPU.SHL_UInt16(this.oCPU.SI.UInt16, this.oCPU.CX.LowUInt8);
			this.oCPU.ES.UInt16 = 0x36fa; // segment
			this.oCPU.AX.UInt16 = this.oCPU.ReadUInt16(this.oCPU.ES.UInt16, (ushort)(this.oCPU.SI.UInt16 + 0x10));
			this.oCPU.AX.UInt16 = this.oCPU.SUB_UInt16(this.oCPU.AX.UInt16, 0xb4);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x28), this.oCPU.ADD_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x28)), this.oCPU.AX.UInt16));
			this.oCPU.AX.UInt16 = this.oCPU.ReadUInt16(this.oCPU.ES.UInt16, (ushort)(this.oCPU.SI.UInt16 + 0x12));
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x28), this.oCPU.SUB_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x28)), this.oCPU.AX.UInt16));
			this.oCPU.ES.UInt16 = 0x36fa; // segment
			this.oCPU.AX.UInt16 = this.oCPU.ReadUInt16(this.oCPU.ES.UInt16, (ushort)(this.oCPU.SI.UInt16 + 0x48));
			this.oCPU.AX.UInt16 = this.oCPU.SUB_UInt16(this.oCPU.AX.UInt16, 0x40);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2c), this.oCPU.ADD_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2c)), this.oCPU.AX.UInt16));
			this.oCPU.AX.UInt16 = this.oCPU.ReadUInt16(this.oCPU.ES.UInt16, (ushort)(this.oCPU.SI.UInt16 + 0x4a));
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2c), this.oCPU.SUB_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2c)), this.oCPU.AX.UInt16));
			
			// Instruction address 0x0000:0x11b3, size: 5
			this.oParent.Graphics.F0_VGA_0c3e_DrawBitmapToScreen(this.oParent.Var_aa_Screen0_Rectangle,
				90, 0,
				this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x12)));

			// Instruction address 0x0000:0x11cb, size: 5
			this.oParent.Graphics.F0_VGA_0c3e_DrawBitmapToScreen(this.oParent.Var_aa_Screen0_Rectangle,
				this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x28)),
				this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2c)) - 2,
				this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x36)));

			// Instruction address 0x0000:0x11e9, size: 5
			this.oParent.CommonTools.PlayTune(this.oParent.GameData.Nations[this.oParent.GameData.Players[playerID].NationalityID].LongTune, 3);

			// Instruction address 0x0000:0x1200, size: 5
			this.oParent.CAPI.strcpy((ushort)(this.oCPU.BP.UInt16 - 0x9), "PAL");

			// Instruction address 0x0000:0x1210, size: 5
			this.oParent.ImageTools.F0_2fa1_01a2_LoadBitmapOrPalette(-1, 0, 0, (ushort)(this.oCPU.BP.UInt16 - 0x10), 0xc1d6);

			// Instruction address 0x0000:0x1220, size: 5
			this.oParent.ImageTools.F0_2fa1_01a2_LoadBitmapOrPalette(-1, 0, 0, "SLAM1.PAL", 0xbdee);

			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2e), 0xc0);

		L122d:
			this.oCPU.BX.UInt16 = this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2e));
			this.oCPU.SI.UInt16 = this.oCPU.BX.UInt16;
			this.oCPU.AX.LowUInt8 = this.oCPU.ReadUInt8(this.oCPU.DS.UInt16, (ushort)(this.oCPU.SI.UInt16 + 0xc1dc));
			this.oCPU.WriteUInt8(this.oCPU.DS.UInt16, (ushort)(this.oCPU.BX.UInt16 + 0xbdf4), this.oCPU.AX.LowUInt8);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2e), this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2e))));
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2e)), 0x1b0);
			if (this.oCPU.Flags.L) goto L122d;

			// Instruction address 0x0000:0x124c, size: 5
			this.oParent.CommonTools.TransformPalette(8, 0xbdee);

			this.oCPU.AX.LowUInt8 = this.oCPU.ReadUInt8(this.oCPU.DS.UInt16, 0xb1d4);
			this.oCPU.CBW(this.oCPU.AX);
			this.oCPU.CX.LowUInt8 = 0x7;
			this.oCPU.IDIV_UInt8(this.oCPU.AX, this.oCPU.CX.LowUInt8);
			this.oCPU.AX.LowUInt8 = this.oCPU.AX.HighUInt8;
			this.oCPU.CBW(this.oCPU.AX);
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x26), this.oCPU.AX.UInt16);
			this.oCPU.TEST_UInt8(this.oCPU.ReadUInt8(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x26)), 0x1);
			if (this.oCPU.Flags.E) goto L1274;
			this.oCPU.CWD(this.oCPU.AX, this.oCPU.DX);
			this.oCPU.AX.UInt16 = this.oCPU.SUB_UInt16(this.oCPU.AX.UInt16, this.oCPU.DX.UInt16);
			this.oCPU.AX.UInt16 = this.oCPU.SAR_UInt16(this.oCPU.AX.UInt16, 0x1);
			this.oCPU.AX.UInt16 = this.oCPU.SUB_UInt16(this.oCPU.AX.UInt16, 0x6);
			this.oCPU.AX.UInt16 = this.oCPU.NEG_UInt16(this.oCPU.AX.UInt16);
			goto L127d;

		L1274:
			this.oCPU.CX.UInt16 = 0x2;
			this.oCPU.AX.UInt16 = this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x26));
			this.oCPU.CWD(this.oCPU.AX, this.oCPU.DX);
			this.oCPU.IDIV_UInt16(this.oCPU.AX, this.oCPU.DX, this.oCPU.CX.UInt16);

		L127d:
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x26), this.oCPU.AX.UInt16);
			this.oCPU.AX.LowUInt8 = this.oCPU.ReadUInt8(this.oCPU.DS.UInt16, 0xb1d4);
			this.oCPU.WriteUInt8(this.oCPU.DS.UInt16, 0xb1d4, this.oCPU.INC_UInt8(this.oCPU.ReadUInt8(this.oCPU.DS.UInt16, 0xb1d4)));
			this.oCPU.CMP_UInt8(this.oCPU.AX.LowUInt8, 0x7);
			if (this.oCPU.Flags.L) goto L128f;
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x26), this.oCPU.ADD_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x26)), 0x7));

		L128f:
			this.oCPU.AX.LowUInt8 = this.oCPU.ReadUInt8(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x32));
			this.oCPU.BX.UInt16 = this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x26));
			this.oCPU.ES.UInt16 = 0x3772; // segment
			this.oCPU.WriteUInt8(this.oCPU.ES.UInt16, (ushort)(this.oCPU.BX.UInt16 + 0x37c4), this.oCPU.AX.LowUInt8);

			// Instruction address 0x0000:0x129e, size: 5
			this.oParent.CommonTools.ResetWaitTimer();

			// Instruction address 0x0000:0x12ab, size: 5
			this.oParent.ImageTools.F0_2fa1_01a2_LoadBitmapOrPalette(1, 0, 0, "SLAM1.PIC", 0);

			// Instruction address 0x0000:0x12c5, size: 5
			this.oParent.ImageTools.F0_2fa1_01a2_LoadBitmapOrPalette(1, 0, 133, (ushort)(this.oCPU.BP.UInt16 - 0x24), 0);

			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2e), 0x0);

		L12d2:
			this.oCPU.BX.UInt16 = this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2e));
			this.oCPU.ES.UInt16 = 0x3772; // segment

			if (this.oCPU.ReadUInt8(this.oCPU.ES.UInt16, (ushort)(this.oCPU.BX.UInt16 + 0x37c4)) != 0xff)
			{
				this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2a),
					this.oCPU.ReadUInt8(this.oCPU.ES.UInt16, (ushort)(this.oCPU.BX.UInt16 + 0x37c4)));

				// Instruction address 0x0000:0x1344, size: 5
				this.oParent.Graphics.F0_VGA_07d8_DrawImage(this.oParent.Var_19d4_Screen1_Rectangle,
					((this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2a)) % 7) * 28) + 1,
					((this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2a)) / 7) * 34) + 133,
					27, 33,
					this.oParent.Var_19d4_Screen1_Rectangle,
					((this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2e)) % 7) * 46) + 8,
					((-(this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2e)) / 7)) * 42) + 49);
			}
		
			this.oCPU.WriteUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2e), this.oCPU.INC_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2e))));
			this.oCPU.CMP_UInt16(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2e)), 0xe);
			if (this.oCPU.Flags.GE) goto L1358;
			goto L12d2;

		L1358:
			goto L135f;

		L135a:
			this.oCPU.WriteUInt8(this.oCPU.DS.UInt16, 0xba06, 0x0);

		L135f:
			this.oCPU.AX.UInt16 = this.oParent.Var_5c_TickCount;
			this.oCPU.DoEvents();
			this.oCPU.CMP_UInt16(this.oCPU.AX.UInt16, 0xf0);
			if (this.oCPU.Flags.L) goto L135a;

			// Instruction address 0x0000:0x138a, size: 5
			this.oParent.CAPI.strcat(
				0xba06,
				ClassicGameText.Current.Format(
					ClassicGameTextKey.ReplayDestroyLine,
					FormatReplayYear((short)param2),
					GetLocalizedNation(
						this.oParent.GameData.HumanPlayerID)));

			// Instruction address 0x0000:0x13f3, size: 5
			this.oParent.DrawTools.F0_1182_00b3_DrawCenteredStringToScreen0(0xba06, 160, 152, 20);

			// Instruction address 0x0000:0x1417, size: 5
			this.oParent.DrawTools.F0_1182_00b3_DrawCenteredStringToScreen0(0xba06, 160, 151, 23);
			
			// Instruction address 0x0000:0x1427, size: 5
			this.oParent.CAPI.strcpy(
				0xba06,
				ClassicGameText.Current.Format(
					ClassicGameTextKey.ReplayDestroyedCivilizationLine,
					GetLocalizedNation(
						playerID,
						useNationality: true)));

			// Instruction address 0x0000:0x1464, size: 5
			this.oParent.DrawTools.F0_1182_00b3_DrawCenteredStringToScreen0(0xba06, 160, 168, 20);

			// Instruction address 0x0000:0x1488, size: 5
			this.oParent.DrawTools.F0_1182_00b3_DrawCenteredStringToScreen0(0xba06, 160, 167, 23);

			// Instruction address 0x0000:0x14ae, size: 5
			this.oParent.Graphics.F0_VGA_07d8_DrawImage(this.oParent.Var_aa_Screen0_Rectangle, 0, 133, 320, 67, this.oParent.Var_19d4_Screen1_Rectangle, 0, 133);

			// Instruction address 0x0000:0x14c6, size: 5
			this.oParent.Graphics.F0_VGA_0c3e_DrawBitmapToScreen(this.oParent.Var_aa_Screen0_Rectangle,
				this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x28)),
				this.oCPU.ReadInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x2c)) - 2,
				this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x30)));

			// Instruction address 0x0000:0x14d1, size: 5
			this.oParent.Tools.F0_2dc4_0523_FreeResource(this.oCPU.ReadUInt16(this.oCPU.SS.UInt16, (ushort)(this.oCPU.BP.UInt16 - 0x12)), "");

			// Instruction address 0x0000:0x14dd, size: 5
			this.oParent.CommonTools.PlayTune(1, 0);

			// Instruction address 0x0000:0x14e9, size: 5
			this.oParent.CommonTools.WaitTimer(60);

			// Instruction address 0x0000:0x1508, size: 5
			this.oParent.CommonTools.PlayTune(
				this.oParent.GameData.Nations[this.oParent.GameData.Players[this.oParent.GameData.HumanPlayerID].NationalityID].LongTune, 3);

			// Instruction address 0x0000:0x1518, size: 5
			this.oParent.Graphics.F0_VGA_06b7_DrawScreenToMainScreenWithEffect(1);

			// Instruction address 0x0000:0x1538, size: 5
			this.oParent.Graphics.F0_VGA_07d8_DrawImage(this.oParent.Var_19d4_Screen1_Rectangle, 0, 0, 320, 200, this.oParent.Var_aa_Screen0_Rectangle, 0, 0);

			// Instruction address 0x0000:0x1543, size: 5
			this.oParent.CommonTools.F0_1000_0846(0);
			
			// Instruction address 0x0000:0x154f, size: 5
			this.oParent.CommonTools.PlayTune(1, 0);

			this.oCPU.SI.UInt16 = this.oCPU.POP_UInt16();
			this.oCPU.SP.UInt16 = this.oCPU.BP.UInt16;
			this.oCPU.BP.UInt16 = this.oCPU.POP_UInt16();
			// Far return
			this.oCPU.Log.ExitBlock("F9_0000_0f79");
		}
	}
}
