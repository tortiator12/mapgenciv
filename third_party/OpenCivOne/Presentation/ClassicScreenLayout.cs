namespace OpenCivOne.Presentation;

public readonly record struct ClassicScreenLayout(int Columns, int Rows)
{
	public static ClassicScreenLayout ForVisibleScreenCount(int count) => count switch
	{
		0 or 1 => new ClassicScreenLayout(1, 1),
		2 => new ClassicScreenLayout(2, 1),
		3 or 4 => new ClassicScreenLayout(2, 2),
		_ => throw new ArgumentOutOfRangeException(
			nameof(count),
			count,
			"OpenCivOne supports between zero and four visible screens."),
	};
}
