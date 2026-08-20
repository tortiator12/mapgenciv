using System.Xml.Serialization;

namespace OpenCivOne
{
	public class GameSettings
	{
		private int settingsValue = 2;

		/// <summary>
		/// Shows the Instant advices. Represents bit value 0x1
		/// </summary>
		public bool InstantAdvice
		{
			get => (settingsValue & (1 << 0)) != 0;
			set
			{
				this.settingsValue |= (1 << 0);
				if (!value)
					this.settingsValue ^= (1 << 0);
			}
		}

		/// <summary>
		/// Automatically saves the game every N turns. Represents bit value 0x2
		/// </summary>
		public bool AutoSave
		{
			get => (settingsValue & (1 << 1)) != 0;
			set
			{
				this.settingsValue |= (1 << 1);
				if (!value)
					this.settingsValue ^= (1 << 1);
			}
		}

		/// <summary>
		/// Waits for End of Turn confirmation. Represents bit value 0x4
		/// </summary>
		public bool EndOfTurn
		{
			get => (settingsValue & (1 << 2)) != 0;
			set
			{
				this.settingsValue |= (1 << 2);
				if (!value)
					this.settingsValue ^= (1 << 2);
			}
		}

		/// <summary>
		/// Shows animations. Represents bit value 0x8
		/// </summary>
		public bool Animations
		{
			get => (settingsValue & (1 << 3)) != 0;
			set
			{
				this.settingsValue |= (1 << 3);
				if (!value)
					this.settingsValue ^= (1 << 3);
			}
		}

		/// <summary>
		/// Enable sound. Represents bit value 0x10
		/// </summary>
		public bool Sound
		{
			get => (settingsValue & (1 << 4)) != 0;
			set
			{
				this.settingsValue |= (1 << 4);
				if (!value)
					this.settingsValue ^= (1 << 4);
			}
		}

		/// <summary>
		/// Shows enemy moves for visible units. Represents bit value 0x20
		/// </summary>
		public bool EnemyMoves
		{
			get => (settingsValue & (1 << 5)) != 0;
			set
			{
				this.settingsValue |= (1 << 5);
				if (!value)
					this.settingsValue ^= (1 << 5);
			}
		}

		/// <summary>
		/// Shows the text from Encyclopedia. Represents bit value 0x40
		/// </summary>
		public bool EncyclopediaText
		{
			get => (settingsValue & (1 << 6)) != 0;
			set
			{
				this.settingsValue |= (1 << 6);
				if (!value)
					this.settingsValue ^= (1 << 6);
			}
		}

		/// <summary>
		/// Are we building palace. Represents bit value 0x80
		/// </summary>
		public bool BuildPalace
		{
			get => (settingsValue & (1 << 7)) != 0;
			set
			{
				this.settingsValue |= (1 << 7);
				if (!value)
					this.settingsValue ^= (1 << 7);
			}
		}

		/// <summary>
		/// Enable debug saves for every turn. Represents bit value 0x80
		/// </summary>
		public bool DebugSaves
		{
			get => (settingsValue & (1 << 8)) != 0;
			set
			{
				this.settingsValue |= (1 << 8);
				if (!value)
					this.settingsValue ^= (1 << 8);
			}
		}

		/// <summary>
		/// Makes the automatic-explore order available. Represents bit value
		/// 0x200. Disabled for original and older saves.
		/// </summary>
		public bool AutomaticExplore
		{
			get => (settingsValue & (1 << 9)) != 0;
			set
			{
				this.settingsValue |= (1 << 9);
				if (!value)
					this.settingsValue ^= (1 << 9);
			}
		}

		/// <summary>
		/// Makes the nearest-city Settler improvement order available.
		/// Represents bit value 0x400. Disabled for original and older saves.
		/// </summary>
		public bool ImproveNearestCity
		{
			get => (settingsValue & (1 << 10)) != 0;
			set
			{
				this.settingsValue |= (1 << 10);
				if (!value)
					this.settingsValue ^= (1 << 10);
			}
		}

		/// <summary>
		/// Makes the build-road-to-city Settler order available. Represents
		/// bit value 0x800. Disabled for original and older saves.
		/// </summary>
		public bool BuildRoadToCity
		{
			get => (settingsValue & (1 << 11)) != 0;
			set
			{
				this.settingsValue |= (1 << 11);
				if (!value)
					this.settingsValue ^= (1 << 11);
			}
		}

		/// <summary>
		/// Allows the human player's units to be assigned to another safe
		/// home city before original shield support would disband them.
		/// Represents bit value 0x1000. Disabled for original and older saves.
		/// </summary>
		public bool AutomaticHomeCityReassignment
		{
			get => (settingsValue & (1 << 12)) != 0;
			set
			{
				this.settingsValue |= (1 << 12);
				if (!value)
					this.settingsValue ^= (1 << 12);
			}
		}

		/// <summary>
		/// Draws the human player's active Go To routes on the main map.
		/// Represents bit value 0x2000. Disabled for original and older saves.
		/// </summary>
		public bool ShowGoToPaths
		{
			get => (settingsValue & (1 << 13)) != 0;
			set
			{
				this.settingsValue |= (1 << 13);
				if (!value)
					this.settingsValue ^= (1 << 13);
			}
		}

		/// <summary>
		/// Shows the human player a read-only Caravan destination suggestion.
		/// Represents bit value 0x4000. Disabled for original and older saves.
		/// </summary>
		public bool CaravanTradeAdvisor
		{
			get => (settingsValue & (1 << 14)) != 0;
			set
			{
				this.settingsValue |= (1 << 14);
				if (!value)
					this.settingsValue ^= (1 << 14);
			}
		}

		public void Disable1991PlusOptions()
		{
			this.AutomaticExplore = false;
			this.ImproveNearestCity = false;
			this.BuildRoadToCity = false;
			this.AutomaticHomeCityReassignment = false;
			this.ShowGoToPaths = false;
			this.CaravanTradeAdvisor = false;
		}

		public void EnableSmartAutomationDefaults()
		{
			this.AutomaticExplore = true;
			this.ImproveNearestCity = true;
			this.BuildRoadToCity = true;
		}

		public void Enable1991PlusDefaults()
		{
			// 1991+ starts with uninterrupted turn flow. The original save
			// bit has inverse semantics: false means that no separate
			// end-of-turn confirmation is requested.
			this.EndOfTurn = false;
			this.AutomaticExplore = true;
			this.ImproveNearestCity = true;
			this.BuildRoadToCity = true;
			this.AutomaticHomeCityReassignment = true;
			this.ShowGoToPaths = true;
			this.CaravanTradeAdvisor = true;
		}

		public bool HasSmartAutomationOptionEnabled() =>
			this.AutomaticExplore ||
			this.ImproveNearestCity ||
			this.BuildRoadToCity;

		public bool Has1991PlusOptionsEnabled() =>
			this.AutomaticExplore ||
			this.ImproveNearestCity ||
			this.BuildRoadToCity ||
			this.AutomaticHomeCityReassignment ||
			this.ShowGoToPaths ||
			this.CaravanTradeAdvisor;

		[XmlIgnore]
		public int Value
		{
			get
			{
				return this.settingsValue;
			}
			set
			{
				this.settingsValue = value;
			}
		}
	}
}
