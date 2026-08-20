using OpenCivOne.Graphics;
using OpenCivOne.Runtime;

namespace OpenCivOne;

public readonly record struct ClassicCaravanTradeRecommendation(
	int CityID,
	bool IsExact,
	int? Payout,
	int? TradeBonus,
	bool HasKnownLandRoute,
	int? KnownLandRouteSteps,
	int VisibleSize,
	int Distance,
	bool IsForeign,
	int EstimatedPayout,
	bool IsExistingTradeRoute);

/// <summary>
/// Read-only 1991+ advisor for a human Caravan. Candidate discovery and
/// ranking use only the human player's known map and visible city data.
/// Exact foreign economic values are exposed only when an embassy exists.
/// </summary>
public static class ClassicCaravanTradeAdvisor
{
	private const int DirectionCount = 8;

	private static readonly GPoint[] MoveDirections =
	[
		new GPoint(0, 0),
		new GPoint(0, -1),
		new GPoint(1, -1),
		new GPoint(1, 0),
		new GPoint(1, 1),
		new GPoint(0, 1),
		new GPoint(-1, 1),
		new GPoint(-1, 0),
		new GPoint(-1, -1)
	];

	public static bool TryRecommend(
		OpenCivOneGame game,
		int playerID,
		int unitID,
		out ClassicCaravanTradeRecommendation recommendation)
	{
		ArgumentNullException.ThrowIfNull(game);
		recommendation = default;
		GameData gameData = game.GameData;

		if (!ClassicAiRuntimeProfiles.UsesSmartEnhancements(
				gameData.AiProfile) ||
			!gameData.GameSettingFlags.CaravanTradeAdvisor ||
			playerID != gameData.HumanPlayerID ||
			playerID <= 0 ||
			playerID >= gameData.Players.Length ||
			unitID < 0 ||
			unitID >= gameData.Players[playerID].Units.Length)
		{
			return false;
		}

		Unit caravan = gameData.Players[playerID].Units[unitID];
		if (caravan.UnitType != UnitTypeEnum.Caravan ||
			caravan.PlayerID != playerID ||
			caravan.HomeCityID < 0 ||
			caravan.HomeCityID >= gameData.Cities.Length)
		{
			return false;
		}

		City homeCity = gameData.Cities[caravan.HomeCityID];
		if (!IsActiveCity(homeCity) ||
			homeCity.PlayerID != playerID)
		{
			return false;
		}

		List<ClassicCaravanTradeRecommendation> candidates = [];
		for (int cityID = 0; cityID < gameData.Cities.Length; cityID++)
		{
			City destination = gameData.Cities[cityID];
			if (cityID == caravan.HomeCityID ||
				destination.Position == caravan.Position ||
				!IsKnownDestination(gameData, playerID, destination) ||
				!CanEstablishClassicTrade(
					game,
					playerID,
					homeCity,
					destination))
			{
				continue;
			}

			bool isForeign = destination.PlayerID != playerID;
			bool hasEmbassy =
				!isForeign ||
				gameData.Players[playerID]
					.Diplomacy[destination.PlayerID]
					.HasFlag(DiplomacyFlagsEnum.Unknown40);
			int distance =
				game.Tools.F0_2dc4_0289_GetShortestDistance(
					homeCity.Position,
					destination.Position);
			int? routeSteps = GetKnownLandRouteSteps(
				gameData,
				game.MapManagement,
				playerID,
				caravan.Position,
				destination.Position);
			int? payout = null;
			int? tradeBonus = null;

			if (hasEmbassy)
			{
				payout = CalculateExactPayout(
					gameData,
					game.MapManagement,
					playerID,
					homeCity,
					destination,
					distance);
				tradeBonus = CalculateExactTradeBonusChange(
					gameData,
					playerID,
					homeCity,
					destination);
			}

			int estimatedPayout =
				payout ??
				CalculatePublicPayoutEstimate(
					game.MapManagement,
					playerID,
					homeCity,
					destination,
					distance);
			candidates.Add(
				new ClassicCaravanTradeRecommendation(
					cityID,
					hasEmbassy,
					payout,
					tradeBonus,
					routeSteps.HasValue,
					routeSteps,
					isForeign
						? Math.Max(0, (int)destination.VisibleSize)
						: Math.Max(0, (int)destination.ActualSize),
					distance,
					isForeign,
					estimatedPayout,
					homeCity.TradeCityIDs.Contains(
						(sbyte)destination.ID)));
		}

		if (candidates.Count == 0)
		{
			return false;
		}

		// Rank the economic result before travel convenience. Classic's
		// foreign and overseas multipliers are large enough that an easy but
		// nearly worthless domestic route must not hide a much stronger
		// known destination. Without an embassy the estimate uses only
		// public city size, ownership, distance and continent information.
		candidates.Sort(CompareCandidates);
		recommendation = candidates[0];
		return true;
	}

	private static int CompareCandidates(
		ClassicCaravanTradeRecommendation left,
		ClassicCaravanTradeRecommendation right)
	{
		// A Caravan can collect the one-time payout repeatedly, but an
		// already connected destination cannot establish a second permanent
		// route. The route advisor therefore prefers a still-unconnected
		// destination whenever one is available.
		int comparison = left.IsExistingTradeRoute.CompareTo(
			right.IsExistingTradeRoute);
		if (comparison != 0)
		{
			return comparison;
		}

		comparison = right.EstimatedPayout.CompareTo(
			left.EstimatedPayout);
		if (comparison != 0)
		{
			return comparison;
		}

		comparison = Nullable.Compare(
			right.TradeBonus,
			left.TradeBonus);
		if (comparison != 0)
		{
			return comparison;
		}

		comparison = right.IsForeign.CompareTo(left.IsForeign);
		if (comparison != 0)
		{
			return comparison;
		}

		comparison = right.HasKnownLandRoute.CompareTo(
			left.HasKnownLandRoute);
		if (comparison != 0)
		{
			return comparison;
		}

		comparison = Nullable.Compare(
			left.KnownLandRouteSteps,
			right.KnownLandRouteSteps);
		if (comparison != 0)
		{
			return comparison;
		}

		return left.CityID.CompareTo(right.CityID);
	}

	private static int CalculatePublicPayoutEstimate(
		MapManagement mapManagement,
		int playerID,
		City homeCity,
		City destination,
		int distance)
	{
		int destinationSize =
			destination.PlayerID == playerID
				? Math.Max(1, (int)destination.ActualSize)
				: Math.Max(1, (int)destination.VisibleSize);
		int tradeProxy =
			Math.Max(1, (int)homeCity.ActualSize) +
			destinationSize;
		int estimate =
			(distance + 10) *
			tradeProxy /
			24;
		if (mapManagement.F0_2aea_1942_GetGroupID(
				homeCity.Position) ==
			mapManagement.F0_2aea_1942_GetGroupID(
				destination.Position))
		{
			estimate /= 2;
		}

		if (destination.PlayerID == playerID)
		{
			estimate /= 2;
		}

		return Math.Max(1, estimate);
	}

	private static bool IsKnownDestination(
		GameData gameData,
		int playerID,
		City city)
	{
		if (!IsActiveCity(city) ||
			city.PlayerID <= 0 ||
			city.PlayerID >= gameData.Players.Length)
		{
			return false;
		}

		if (city.PlayerID == playerID)
		{
			return true;
		}

		return city.VisibleSize > 0 &&
			IsKnownCell(gameData, playerID, city.Position);
	}

	private static bool IsActiveCity(City city) =>
		city.StatusFlag != 0xff &&
		city.ActualSize > 0;

	private static bool CanEstablishClassicTrade(
		OpenCivOneGame game,
		int playerID,
		City homeCity,
		City destination)
	{
		if (destination.PlayerID != playerID)
		{
			return true;
		}

		int distance =
			game.Tools.F0_2dc4_0289_GetShortestDistance(
				homeCity.Position,
				destination.Position);
		return distance >= 10 ||
			game.MapManagement.F0_2aea_1942_GetGroupID(
				homeCity.Position) !=
			game.MapManagement.F0_2aea_1942_GetGroupID(
				destination.Position);
	}

	private static int CalculateExactPayout(
		GameData gameData,
		MapManagement mapManagement,
		int playerID,
		City homeCity,
		City destination,
		int distance)
	{
		int payout =
			(distance + 10) *
			(destination.BaseTrade + homeCity.BaseTrade) /
			24;
		if (mapManagement.F0_2aea_1942_GetGroupID(
				homeCity.Position) ==
			mapManagement.F0_2aea_1942_GetGroupID(
				destination.Position))
		{
			payout /= 2;
		}

		if (destination.PlayerID == playerID)
		{
			payout /= 2;
		}

		if (HasTechnology(
			gameData,
			destination.PlayerID,
			TechnologyAdvanceEnum.Railroad))
		{
			payout -= payout / 3;
		}

		if (HasTechnology(
			gameData,
			destination.PlayerID,
			TechnologyAdvanceEnum.Flight))
		{
			payout -= payout / 3;
		}

		return payout;
	}

	private static int? CalculateExactTradeBonusChange(
		GameData gameData,
		int playerID,
		City homeCity,
		City destination)
	{
		if (homeCity.TradeCityIDs.Contains((sbyte)destination.ID))
		{
			return 0;
		}

		int destinationWorth = GetRouteReplacementWorth(
			playerID,
			destination);
		int replacementCityID = -1;
		int weakestWorth = int.MaxValue;
		foreach (sbyte tradeCityID in homeCity.TradeCityIDs)
		{
			if (tradeCityID == -1)
			{
				return GetRouteTradeBonus(
					playerID,
					homeCity,
					destination);
			}

			if (tradeCityID < 0 ||
				tradeCityID >= gameData.Cities.Length)
			{
				return null;
			}

			City existingDestination =
				gameData.Cities[tradeCityID];
			if (!CanUseExactCityValues(
					gameData,
					playerID,
					existingDestination))
			{
				return null;
			}

			int existingWorth = GetRouteReplacementWorth(
				playerID,
				existingDestination);
			if (existingWorth < weakestWorth)
			{
				weakestWorth = existingWorth;
				replacementCityID = tradeCityID;
			}
		}

		if (replacementCityID < 0 ||
			destinationWorth <= weakestWorth)
		{
			return 0;
		}

		int destinationBonus = GetRouteTradeBonus(
			playerID,
			homeCity,
			destination);
		int replacedBonus = GetRouteTradeBonus(
			playerID,
			homeCity,
			gameData.Cities[replacementCityID]);
		return Math.Max(0, destinationBonus - replacedBonus);
	}

	private static int GetRouteReplacementWorth(
		int playerID,
		City destination) =>
		destination.BaseTrade *
		(destination.PlayerID == playerID ? 1 : 2);

	private static int GetRouteTradeBonus(
		int playerID,
		City homeCity,
		City destination) =>
		(homeCity.BaseTrade + destination.BaseTrade + 4) /
		(destination.PlayerID == playerID ? 16 : 8);

	private static bool CanUseExactCityValues(
		GameData gameData,
		int playerID,
		City city) =>
		city.PlayerID == playerID ||
		(city.PlayerID > 0 &&
		 city.PlayerID < gameData.Players.Length &&
		 gameData.Players[playerID]
			.Diplomacy[city.PlayerID]
			.HasFlag(DiplomacyFlagsEnum.Unknown40));

	private static bool HasTechnology(
		GameData gameData,
		int playerID,
		TechnologyAdvanceEnum technology) =>
		playerID > 0 &&
		playerID < gameData.Players.Length &&
		(gameData.Players[playerID]
			.DiscoveredTechnologyFlags[(int)technology >> 4] &
			(1 << ((int)technology & 0xf))) != 0;

	private static int? GetKnownLandRouteSteps(
		GameData gameData,
		MapManagement mapManagement,
		int playerID,
		GPoint start,
		GPoint destination)
	{
		int width = gameData.MapVisibility.GetLength(0);
		int height = gameData.MapVisibility.GetLength(1);
		if (!IsInside(start, width, height) ||
			!IsInside(destination, width, height) ||
			!IsKnownCell(gameData, playerID, start) ||
			!IsKnownCell(gameData, playerID, destination) ||
			mapManagement.GetGroupType(start) !=
				TerrainMapGroupTypeEnum.Land ||
			mapManagement.GetGroupType(destination) !=
				TerrainMapGroupTypeEnum.Land)
		{
			return null;
		}

		if (start == destination)
		{
			return 0;
		}

		bool[,] visited = new bool[width, height];
		Queue<(GPoint Position, int Steps)> frontier = new();
		visited[start.X, start.Y] = true;
		frontier.Enqueue((start, 0));

		while (frontier.Count > 0)
		{
			(GPoint position, int steps) = frontier.Dequeue();
			for (int direction = 1;
				direction <= DirectionCount;
				direction++)
			{
				GPoint offset = MoveDirections[direction];
				GPoint next = new(
					mapManagement.AdjustXPosition(
						position.X + offset.X),
					position.Y + offset.Y);
				if (!IsInside(next, width, height) ||
					visited[next.X, next.Y] ||
					!IsKnownCell(gameData, playerID, next) ||
					mapManagement.GetGroupType(next) !=
						TerrainMapGroupTypeEnum.Land)
				{
					continue;
				}

				if (next == destination)
				{
					return steps + 1;
				}

				visited[next.X, next.Y] = true;
				frontier.Enqueue((next, steps + 1));
			}
		}

		return null;
	}

	private static bool IsKnownCell(
		GameData gameData,
		int playerID,
		GPoint position) =>
		IsInside(
			position,
			gameData.MapVisibility.GetLength(0),
			gameData.MapVisibility.GetLength(1)) &&
		(gameData.MapVisibility[position.X, position.Y] &
			(1 << playerID)) != 0;

	private static bool IsInside(
		GPoint position,
		int width,
		int height) =>
		position.X >= 0 &&
		position.X < width &&
		position.Y >= 0 &&
		position.Y < height;
}
