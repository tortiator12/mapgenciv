using System.Security.Cryptography;
using System.Text;
using OpenCivOne.Platform;
using OpenCivOne.Runtime;

namespace OpenCivOne;

/// <summary>
/// Holds Project1991-only per-unit orders without changing the original
/// twelve-byte Civilization unit record.
/// </summary>
public sealed class ClassicUnitAutomationState
{
	private static readonly byte[] FingerprintPrefix =
		Encoding.ASCII.GetBytes(
			"project1991-unit-automation/1");

	private readonly object synchronization = new();
	private Dictionary<(int PlayerID, int UnitID),
		ClassicUnitAutomationOrderMetadata> orders = [];

	public int Count
	{
		get
		{
			lock (this.synchronization)
			{
				return this.orders.Count;
			}
		}
	}

	public IReadOnlyList<ClassicUnitAutomationOrderMetadata>
		Orders
	{
		get
		{
			lock (this.synchronization)
			{
				return this.orders.Values
					.OrderBy(static order => order.PlayerID)
					.ThenBy(static order => order.UnitID)
					.ToArray();
			}
		}
	}

	public void Clear()
	{
		lock (this.synchronization)
		{
			this.orders = [];
		}
	}

	public bool Cancel(int playerID, int unitID)
	{
		lock (this.synchronization)
		{
			return this.orders.Remove((playerID, unitID));
		}
	}

	public int CancelKind(ClassicUnitAutomationKind kind)
	{
		lock (this.synchronization)
		{
			(int PlayerID, int UnitID)[] matchingKeys =
				this.orders
					.Where(pair => pair.Value.Kind == kind)
					.Select(pair => pair.Key)
					.ToArray();
			foreach ((int PlayerID, int UnitID) key in matchingKeys)
			{
				this.orders.Remove(key);
			}

			return matchingKeys.Length;
		}
	}

	public bool TryGetOrder(
		GameData gameData,
		int playerID,
		int unitID,
		ClassicUnitAutomationKind kind,
		out ClassicUnitAutomationOrderMetadata order)
	{
		ArgumentNullException.ThrowIfNull(gameData);
		lock (this.synchronization)
		{
			if (!this.orders.TryGetValue(
					(playerID, unitID),
					out ClassicUnitAutomationOrderMetadata? candidate) ||
				candidate.Kind != kind)
			{
				order = null!;
				return false;
			}

			if (!TryGetApplicableUnit(
				gameData,
				playerID,
				unitID,
				kind,
				candidate.UnitTypeID,
				out _))
			{
				this.orders.Remove((playerID, unitID));
				order = null!;
				return false;
			}

			order = candidate;
			return true;
		}
	}

	public bool TrySetOrder(
		GameData gameData,
		int playerID,
		int unitID,
		ClassicUnitAutomationKind kind,
		ClassicUnitAutomationPhase phase,
		int? destinationCityID = null,
		int? targetX = null,
		int? targetY = null,
		ClassicUnitAutomationWorkKind? workKind = null)
	{
		ArgumentNullException.ThrowIfNull(gameData);
		if (!TryGetApplicableUnit(
			gameData,
			playerID,
			unitID,
			kind,
			expectedUnitTypeID: null,
			out Unit? unit))
		{
			return false;
		}

		ClassicUnitAutomationOrderMetadata order = new(
			playerID,
			unitID,
			(int)unit.UnitType,
			kind,
			phase,
			destinationCityID,
			targetX,
			targetY,
			workKind,
			ComputeUnitStateFingerprint(
				playerID,
				unitID,
				unit));
		try
		{
			ClassicSaveMetadataSerializer
				.ValidateUnitAutomationForSerialize(
					new ClassicUnitAutomationMetadata([order]));
		}
		catch (InvalidDataException)
		{
			return false;
		}

		lock (this.synchronization)
		{
			this.orders[(playerID, unitID)] = order;
		}
		return true;
	}

	public ClassicUnitAutomationMetadata CreateSaveMetadata(
		GameData gameData)
	{
		ArgumentNullException.ThrowIfNull(gameData);
		Dictionary<(int PlayerID, int UnitID),
			ClassicUnitAutomationOrderMetadata> reconciled = [];

		lock (this.synchronization)
		{
			foreach (ClassicUnitAutomationOrderMetadata order in
				this.orders.Values)
			{
				if (!TryGetApplicableUnit(
					gameData,
					order.PlayerID,
					order.UnitID,
					order.Kind,
					order.UnitTypeID,
					out Unit? unit))
				{
					continue;
				}

				ClassicUnitAutomationOrderMetadata currentOrder =
					order with
					{
						UnitStateFingerprint =
							ComputeUnitStateFingerprint(
								order.PlayerID,
								order.UnitID,
								unit),
					};
				reconciled[
					(order.PlayerID, order.UnitID)] =
						currentOrder;
			}

			this.orders = reconciled;
			return new ClassicUnitAutomationMetadata(
				reconciled.Values);
		}
	}

	/// <summary>
	/// Replaces the complete live order set only after every candidate has
	/// been checked against the successfully loaded legacy state.
	/// Structurally valid but stale orders are discarded.
	/// </summary>
	public int ReplaceFromSave(
		GameData gameData,
		ClassicUnitAutomationMetadata metadata)
	{
		ArgumentNullException.ThrowIfNull(gameData);
		ArgumentNullException.ThrowIfNull(metadata);
		ClassicSaveMetadataSerializer
			.ValidateUnitAutomationForSerialize(metadata);

		Dictionary<(int PlayerID, int UnitID),
			ClassicUnitAutomationOrderMetadata> restored = [];
		int rejectedOrderCount = 0;
		foreach (ClassicUnitAutomationOrderMetadata order in
			metadata.Orders)
		{
			if (!TryGetApplicableUnit(
					gameData,
					order.PlayerID,
					order.UnitID,
					order.Kind,
					order.UnitTypeID,
					out Unit? unit) ||
				!string.Equals(
					order.UnitStateFingerprint,
					ComputeUnitStateFingerprint(
						order.PlayerID,
						order.UnitID,
						unit),
					StringComparison.Ordinal))
			{
				rejectedOrderCount++;
				continue;
			}

			restored[(order.PlayerID, order.UnitID)] =
				order;
		}

		lock (this.synchronization)
		{
			this.orders = restored;
		}
		return rejectedOrderCount;
	}

	public static string ComputeUnitStateFingerprint(
		int playerID,
		int unitID,
		Unit unit)
	{
		ArgumentNullException.ThrowIfNull(unit);
		using MemoryStream payload = new();
		payload.Write(FingerprintPrefix);
		LoadAndSave.WriteInt16(payload, checked((short)playerID));
		LoadAndSave.WriteInt16(payload, checked((short)unitID));
		unit.ToStream(payload);
		return Convert.ToHexString(
				SHA256.HashData(payload.ToArray()))
			.ToLowerInvariant();
	}

	private static bool TryGetApplicableUnit(
		GameData gameData,
		int playerID,
		int unitID,
		ClassicUnitAutomationKind kind,
		int? expectedUnitTypeID,
		out Unit unit)
	{
		unit = null!;
		if (!ClassicAiRuntimeProfiles.UsesSmartEnhancements(
				gameData.AiProfile) ||
			playerID != gameData.HumanPlayerID ||
			playerID < 0 ||
			playerID >= gameData.Players.Length ||
			unitID < 0 ||
			unitID >= 128 ||
			!IsKindEnabled(gameData.GameSettingFlags, kind))
		{
			return false;
		}

		unit = gameData.Players[playerID].Units[unitID];
		if (unit.UnitType == UnitTypeEnum.None ||
			(expectedUnitTypeID is not null &&
			 (int)unit.UnitType != expectedUnitTypeID.Value))
		{
			return false;
		}

		return kind ==
				ClassicUnitAutomationKind.AutomaticExplore ||
			unit.UnitType == UnitTypeEnum.Settler;
	}

	private static bool IsKindEnabled(
		GameSettings settings,
		ClassicUnitAutomationKind kind) =>
		kind switch
		{
			ClassicUnitAutomationKind.AutomaticExplore =>
				settings.AutomaticExplore,
			ClassicUnitAutomationKind.ImproveNearestCity =>
				settings.ImproveNearestCity,
			ClassicUnitAutomationKind.BuildRoadToCity =>
				settings.BuildRoadToCity,
			_ => false,
		};
}
