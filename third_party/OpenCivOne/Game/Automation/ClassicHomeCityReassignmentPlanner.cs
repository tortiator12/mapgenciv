namespace OpenCivOne
{
	public enum ClassicHomeCityReassignmentDecision
	{
		Disabled,
		Completed,
		Incomplete,
		NotHumanPlayer
	}

	/// <summary>
	/// A conservative city support projection captured before the original
	/// city phase. All capacities are proven remaining capacities before any
	/// reassignment in the current planning batch.
	/// </summary>
	public readonly record struct ClassicHomeCitySupportSnapshot(
		int CityID,
		int PlayerID,
		bool IsActive,
		int FreeUnitSupportSlots,
		int AvailableShieldSupport,
		int FoodSurplus,
		int UnrestHeadroom);

	/// <summary>
	/// The immutable unit facts needed to reproduce the original choice of
	/// the unit farthest from its home city.
	/// </summary>
	public readonly record struct ClassicHomeCityUnitSnapshot(
		int UnitID,
		int PlayerID,
		int HomeCityID,
		UnitTypeEnum UnitType,
		UnitMovementTypeEnum MovementType,
		int AttackStrength,
		int OriginalDistanceFromHomeCity);

	/// <summary>
	/// A caller-projected distance to one candidate city. IsInsideCity is
	/// explicit because Republic/Democracy unrest depends on it. Missing
	/// relations are treated as unknown and therefore unsafe.
	/// </summary>
	public readonly record struct ClassicHomeCityRelationSnapshot(
		int UnitID,
		int CityID,
		int Distance,
		bool IsInsideCity);

	public readonly record struct ClassicHomeCitySupportFailureSnapshot(
		int CityID,
		int RequiredDisbandCount,
		int RequiredUnitID = -1);

	public sealed record ClassicHomeCityReassignmentSnapshot(
		int PlayerID,
		int HumanPlayerID,
		int GovernmentType,
		bool HasWomensSuffrage,
		IReadOnlyList<ClassicHomeCitySupportSnapshot> Cities,
		IReadOnlyList<ClassicHomeCityUnitSnapshot> Units,
		IReadOnlyList<ClassicHomeCityRelationSnapshot> Relations,
		IReadOnlyList<ClassicHomeCitySupportFailureSnapshot> Failures);

	public readonly record struct ClassicHomeCityReassignment(
		int UnitID,
		int PreviousHomeCityID,
		int NewHomeCityID);

	public sealed record ClassicHomeCityReassignmentPlan(
		ClassicHomeCityReassignmentDecision Decision,
		IReadOnlyList<ClassicHomeCityReassignment> Reassignments,
		IReadOnlyList<int> UnresolvedUnitIDs,
		int UnresolvedSupportCount);

	/// <summary>
	/// Pure, deterministic planner for the optional Project1991 quality-of-
	/// life rule which attempts to change a human unit's home city before
	/// the original game would disband it.
	///
	/// The planner deliberately consumes a conservative resource snapshot
	/// instead of invoking CityWorker. CityWorker's calculation has UI and
	/// game-state side effects, so calling it speculatively would make this
	/// decision unsafe and non-deterministic.
	/// </summary>
	public static class ClassicHomeCityReassignmentPlanner
	{
		public static ClassicHomeCityReassignmentPlan Plan(
			ClassicHomeCityReassignmentSnapshot snapshot)
		{
			ArgumentNullException.ThrowIfNull(snapshot);
			ArgumentNullException.ThrowIfNull(snapshot.Cities);
			ArgumentNullException.ThrowIfNull(snapshot.Units);
			ArgumentNullException.ThrowIfNull(snapshot.Relations);
			ArgumentNullException.ThrowIfNull(snapshot.Failures);

			if (snapshot.PlayerID != snapshot.HumanPlayerID)
			{
				return new ClassicHomeCityReassignmentPlan(
					ClassicHomeCityReassignmentDecision.NotHumanPlayer,
					Array.Empty<ClassicHomeCityReassignment>(),
					Array.Empty<int>(),
					0);
			}

			Dictionary<int, MutableCityCapacity> capacities =
				CreateCapacities(snapshot);
			Dictionary<(int UnitID, int CityID), ClassicHomeCityRelationSnapshot>
				relations = CreateRelations(snapshot);
			HashSet<int> processedUnits = [];
			List<ClassicHomeCityReassignment> reassignments = [];
			List<int> unresolved = [];
			int unresolvedSupportCount = 0;

			foreach (ClassicHomeCitySupportFailureSnapshot failure in
				snapshot.Failures
					.Where(item => item.RequiredDisbandCount > 0)
					.OrderBy(item => item.CityID))
			{
				for (int index = 0;
					index < failure.RequiredDisbandCount;
					index++)
				{
					ClassicHomeCityUnitSnapshot? candidate =
						SelectOriginalDisbandCandidate(
							snapshot,
							failure,
							processedUnits);

					if (!candidate.HasValue)
					{
						unresolvedSupportCount +=
							failure.RequiredDisbandCount - index;
						break;
					}

					ClassicHomeCityUnitSnapshot unit = candidate.Value;
					processedUnits.Add(unit.UnitID);

					MutableCityCapacity? target = SelectTargetCity(
						snapshot,
						unit,
						failure.CityID,
						capacities,
						relations);

					if (target is null)
					{
						unresolved.Add(unit.UnitID);
						unresolvedSupportCount++;
						continue;
					}

					ReserveCapacity(snapshot, unit, target, relations);
					reassignments.Add(
						new ClassicHomeCityReassignment(
							unit.UnitID,
							failure.CityID,
							target.CityID));
				}
			}

			return new ClassicHomeCityReassignmentPlan(
				unresolvedSupportCount == 0
					? ClassicHomeCityReassignmentDecision.Completed
					: ClassicHomeCityReassignmentDecision.Incomplete,
				reassignments.ToArray(),
				unresolved.ToArray(),
				unresolvedSupportCount);
		}

		private static Dictionary<int, MutableCityCapacity> CreateCapacities(
			ClassicHomeCityReassignmentSnapshot snapshot)
		{
			Dictionary<int, MutableCityCapacity> result = [];

			foreach (ClassicHomeCitySupportSnapshot city in snapshot.Cities)
			{
				if (city.FreeUnitSupportSlots < 0 ||
					city.AvailableShieldSupport < 0 ||
					city.UnrestHeadroom < 0)
				{
					throw new ArgumentOutOfRangeException(
						nameof(snapshot),
						"City support capacities cannot be negative.");
				}

				if (!result.TryAdd(
					city.CityID,
					new MutableCityCapacity(city)))
				{
					throw new ArgumentException(
						"City support snapshots must have unique IDs.",
						nameof(snapshot));
				}
			}

			return result;
		}

		private static Dictionary<
			(int UnitID, int CityID),
			ClassicHomeCityRelationSnapshot> CreateRelations(
				ClassicHomeCityReassignmentSnapshot snapshot)
		{
			Dictionary<
				(int UnitID, int CityID),
				ClassicHomeCityRelationSnapshot> result = [];

			foreach (ClassicHomeCityRelationSnapshot relation in
				snapshot.Relations)
			{
				if (relation.Distance < 0)
				{
					throw new ArgumentOutOfRangeException(
						nameof(snapshot),
						"Unit-to-city distances cannot be negative.");
				}

				if (!result.TryAdd(
					(relation.UnitID, relation.CityID),
					relation))
				{
					throw new ArgumentException(
						"Unit-to-city relations must be unique.",
						nameof(snapshot));
				}
			}

			return result;
		}

		private static ClassicHomeCityUnitSnapshot?
			SelectOriginalDisbandCandidate(
				ClassicHomeCityReassignmentSnapshot snapshot,
				ClassicHomeCitySupportFailureSnapshot failure,
				HashSet<int> processedUnits)
		{
			return snapshot.Units
				.Where(unit =>
					unit.PlayerID == snapshot.PlayerID &&
					unit.HomeCityID == failure.CityID &&
					!processedUnits.Contains(unit.UnitID) &&
					(failure.RequiredUnitID < 0 ||
						unit.UnitID == failure.RequiredUnitID) &&
					IsSupportedUnit(unit.UnitType))
				.OrderByDescending(unit =>
					unit.OriginalDistanceFromHomeCity)
				.ThenBy(unit => unit.UnitID)
				.Cast<ClassicHomeCityUnitSnapshot?>()
				.FirstOrDefault();
		}

		private static MutableCityCapacity? SelectTargetCity(
			ClassicHomeCityReassignmentSnapshot snapshot,
			ClassicHomeCityUnitSnapshot unit,
			int previousHomeCityID,
			Dictionary<int, MutableCityCapacity> capacities,
			Dictionary<
				(int UnitID, int CityID),
				ClassicHomeCityRelationSnapshot> relations)
		{
			return capacities.Values
				.Where(city =>
					city.CityID != previousHomeCityID &&
					city.PlayerID == snapshot.PlayerID &&
					city.IsActive &&
					relations.ContainsKey((unit.UnitID, city.CityID)) &&
					CanSupport(snapshot, unit, city, relations))
				.OrderBy(city =>
					city.FreeUnitSupportSlots > 0 ? 0 : 1)
				.ThenByDescending(city =>
					RemainingShieldSupportAfterAssignment(city))
				.ThenByDescending(city =>
					city.FoodSurplus -
					SettlerFoodCost(snapshot, unit))
				.ThenByDescending(city =>
					city.UnrestHeadroom -
					UnrestCost(
						snapshot,
						unit,
						relations[(unit.UnitID, city.CityID)]))
				.ThenBy(city =>
					relations[(unit.UnitID, city.CityID)].Distance)
				.ThenBy(city => city.CityID)
				.FirstOrDefault();
		}

		private static int RemainingShieldSupportAfterAssignment(
			MutableCityCapacity city)
		{
			return city.AvailableShieldSupport -
				(city.FreeUnitSupportSlots > 0 ? 0 : 1);
		}

		private static bool CanSupport(
			ClassicHomeCityReassignmentSnapshot snapshot,
			ClassicHomeCityUnitSnapshot unit,
			MutableCityCapacity city,
			Dictionary<
				(int UnitID, int CityID),
				ClassicHomeCityRelationSnapshot> relations)
		{
			if (city.FreeUnitSupportSlots <= 0 &&
				city.AvailableShieldSupport <= 0)
			{
				return false;
			}

			int foodCost = SettlerFoodCost(snapshot, unit);

			if (foodCost > 0 &&
				city.FoodSurplus < foodCost)
			{
				return false;
			}

			int unrestCost = UnrestCost(
				snapshot,
				unit,
				relations[(unit.UnitID, city.CityID)]);

			return city.UnrestHeadroom >= unrestCost;
		}

		private static void ReserveCapacity(
			ClassicHomeCityReassignmentSnapshot snapshot,
			ClassicHomeCityUnitSnapshot unit,
			MutableCityCapacity city,
			Dictionary<
				(int UnitID, int CityID),
				ClassicHomeCityRelationSnapshot> relations)
		{
			if (city.FreeUnitSupportSlots > 0)
			{
				city.FreeUnitSupportSlots--;
			}
			else
			{
				city.AvailableShieldSupport--;
			}

			city.FoodSurplus -= SettlerFoodCost(snapshot, unit);
			city.UnrestHeadroom -= UnrestCost(
				snapshot,
				unit,
				relations[(unit.UnitID, city.CityID)]);
		}

		private static int SettlerFoodCost(
			ClassicHomeCityReassignmentSnapshot snapshot,
			ClassicHomeCityUnitSnapshot unit)
		{
			if (unit.UnitType != UnitTypeEnum.Settler)
			{
				return 0;
			}

			// This is the original CityWorker local_48 rule.
			return snapshot.GovernmentType <= 1 ? 1 : 2;
		}

		private static int UnrestCost(
			ClassicHomeCityReassignmentSnapshot snapshot,
			ClassicHomeCityUnitSnapshot unit,
			ClassicHomeCityRelationSnapshot relation)
		{
			if (snapshot.GovernmentType < 4 ||
				unit.AttackStrength == 0 ||
				(unit.MovementType != UnitMovementTypeEnum.Air &&
					relation.IsInsideCity))
			{
				return 0;
			}

			int cost = snapshot.HasWomensSuffrage ? 0 : 1;

			if (snapshot.GovernmentType == 5)
			{
				cost++;
			}

			return cost;
		}

		private static bool IsSupportedUnit(UnitTypeEnum unitType)
		{
			return unitType != UnitTypeEnum.None &&
				unitType != UnitTypeEnum.Diplomat &&
				unitType != UnitTypeEnum.Caravan;
		}

		private sealed class MutableCityCapacity
		{
			public MutableCityCapacity(
				ClassicHomeCitySupportSnapshot snapshot)
			{
				this.CityID = snapshot.CityID;
				this.PlayerID = snapshot.PlayerID;
				this.IsActive = snapshot.IsActive;
				this.FreeUnitSupportSlots =
					snapshot.FreeUnitSupportSlots;
				this.AvailableShieldSupport =
					snapshot.AvailableShieldSupport;
				this.FoodSurplus = snapshot.FoodSurplus;
				this.UnrestHeadroom = snapshot.UnrestHeadroom;
			}

			public int CityID { get; }

			public int PlayerID { get; }

			public bool IsActive { get; }

			public int FreeUnitSupportSlots { get; set; }

			public int AvailableShieldSupport { get; set; }

			public int FoodSurplus { get; set; }

			public int UnrestHeadroom { get; set; }
		}
	}
}
