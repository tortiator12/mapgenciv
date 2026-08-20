namespace OpenCivOne.Platform;

public enum ClassicUnitAutomationKind
{
	AutomaticExplore,
	ImproveNearestCity,
	BuildRoadToCity,
}

public static class ClassicUnitAutomationKindIds
{
	public const string AutomaticExplore = "auto-explore";

	public const string ImproveNearestCity =
		"improve-nearest-city";

	public const string BuildRoadToCity = "road-to-city";

	public static string ToStableId(
		ClassicUnitAutomationKind kind) =>
		kind switch
		{
			ClassicUnitAutomationKind.AutomaticExplore =>
				AutomaticExplore,
			ClassicUnitAutomationKind.ImproveNearestCity =>
				ImproveNearestCity,
			ClassicUnitAutomationKind.BuildRoadToCity =>
				BuildRoadToCity,
			_ => throw new ArgumentOutOfRangeException(
				nameof(kind),
				kind,
				"Unit automation kind is not supported."),
		};

	public static bool TryParseStableId(
		string? stableId,
		out ClassicUnitAutomationKind kind)
	{
		kind = stableId switch
		{
			AutomaticExplore =>
				ClassicUnitAutomationKind.AutomaticExplore,
			ImproveNearestCity =>
				ClassicUnitAutomationKind.ImproveNearestCity,
			BuildRoadToCity =>
				ClassicUnitAutomationKind.BuildRoadToCity,
			_ => default,
		};

		return stableId is
			AutomaticExplore or
			ImproveNearestCity or
			BuildRoadToCity;
	}
}

public enum ClassicUnitAutomationPhase
{
	SelectingTarget,
	MovingToTarget,
	WorkingTarget,
}

public static class ClassicUnitAutomationPhaseIds
{
	public const string SelectingTarget = "selecting-target";

	public const string MovingToTarget = "moving-to-target";

	public const string WorkingTarget = "working-target";

	public static string ToStableId(
		ClassicUnitAutomationPhase phase) =>
		phase switch
		{
			ClassicUnitAutomationPhase.SelectingTarget =>
				SelectingTarget,
			ClassicUnitAutomationPhase.MovingToTarget =>
				MovingToTarget,
			ClassicUnitAutomationPhase.WorkingTarget =>
				WorkingTarget,
			_ => throw new ArgumentOutOfRangeException(
				nameof(phase),
				phase,
				"Unit automation phase is not supported."),
		};

	public static bool TryParseStableId(
		string? stableId,
		out ClassicUnitAutomationPhase phase)
	{
		phase = stableId switch
		{
			SelectingTarget =>
				ClassicUnitAutomationPhase.SelectingTarget,
			MovingToTarget =>
				ClassicUnitAutomationPhase.MovingToTarget,
			WorkingTarget =>
				ClassicUnitAutomationPhase.WorkingTarget,
			_ => default,
		};

		return stableId is
			SelectingTarget or
			MovingToTarget or
			WorkingTarget;
	}
}

public enum ClassicUnitAutomationWorkKind
{
	Road,
	Irrigation,
	Mine,
	Pollution,
}

public static class ClassicUnitAutomationWorkKindIds
{
	public const string Road = "road";

	public const string Irrigation = "irrigation";

	public const string Mine = "mine";

	public const string Pollution = "pollution";

	public static string ToStableId(
		ClassicUnitAutomationWorkKind kind) =>
		kind switch
		{
			ClassicUnitAutomationWorkKind.Road => Road,
			ClassicUnitAutomationWorkKind.Irrigation =>
				Irrigation,
			ClassicUnitAutomationWorkKind.Mine => Mine,
			ClassicUnitAutomationWorkKind.Pollution =>
				Pollution,
			_ => throw new ArgumentOutOfRangeException(
				nameof(kind),
				kind,
				"Unit automation work kind is not supported."),
		};

	public static bool TryParseStableId(
		string? stableId,
		out ClassicUnitAutomationWorkKind kind)
	{
		kind = stableId switch
		{
			Road => ClassicUnitAutomationWorkKind.Road,
			Irrigation =>
				ClassicUnitAutomationWorkKind.Irrigation,
			Mine => ClassicUnitAutomationWorkKind.Mine,
			Pollution =>
				ClassicUnitAutomationWorkKind.Pollution,
			_ => default,
		};

		return stableId is
			Road or Irrigation or Mine or Pollution;
	}
}

public sealed record ClassicUnitAutomationOrderMetadata(
	int PlayerID,
	int UnitID,
	int UnitTypeID,
	ClassicUnitAutomationKind Kind,
	ClassicUnitAutomationPhase Phase,
	int? DestinationCityID,
	int? TargetX,
	int? TargetY,
	ClassicUnitAutomationWorkKind? WorkKind,
	string UnitStateFingerprint)
{
	public string KindID =>
		ClassicUnitAutomationKindIds.ToStableId(this.Kind);

	public string PhaseID =>
		ClassicUnitAutomationPhaseIds.ToStableId(this.Phase);

	public string? WorkKindID =>
		this.WorkKind is null
			? null
			: ClassicUnitAutomationWorkKindIds.ToStableId(
				this.WorkKind.Value);
}

public sealed class ClassicUnitAutomationMetadata
{
	public const int CurrentSchemaVersion = 1;

	public const int MaximumOrderCount = 128;

	public static ClassicUnitAutomationMetadata Empty { get; } =
		new(CurrentSchemaVersion, []);

	public ClassicUnitAutomationMetadata(
		IEnumerable<ClassicUnitAutomationOrderMetadata> orders)
		: this(
			CurrentSchemaVersion,
			orders
				.OrderBy(static order => order.PlayerID)
				.ThenBy(static order => order.UnitID))
	{
	}

	internal ClassicUnitAutomationMetadata(
		int schemaVersion,
		IEnumerable<ClassicUnitAutomationOrderMetadata> orders)
	{
		ArgumentNullException.ThrowIfNull(orders);
		SchemaVersion = schemaVersion;
		Orders = Array.AsReadOnly(orders.ToArray());
	}

	public int SchemaVersion { get; }

	public IReadOnlyList<ClassicUnitAutomationOrderMetadata> Orders
	{
		get;
	}
}
