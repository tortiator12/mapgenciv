namespace OpenCivOne.Localization;

/// <summary>
/// German-first text used by the native Project1991/OpenCivOne shell.
/// Text rendered inside the original 320x200 framebuffer remains sourced from
/// the legal DOS data and is intentionally outside this catalog.
/// </summary>
public static class ClassicShellText
{
	public const string Ok = "OK";
	public const string Cancel = "Abbrechen";
	public const string Abort = "Abbrechen";
	public const string Retry = "Wiederholen";
	public const string Ignore = "Ignorieren";
	public const string Yes = "Ja";
	public const string No = "Nein";
	public const string TryAgain = "Erneut versuchen";
	public const string Continue = "Fortfahren";

	public const string CityNameTitle = "Stadtname";
	public const string CityNamePlaceholder = "Name der Stadt";
	public const string PlayerNameTitle = "Dein Name";
	public const string PlayerNamePlaceholder = "Bitte gib deinen Namen ein";
	public const string NationNameTitle = "Name des Volkes";
	public const string NationNamePlaceholder = "Zum Beispiel „Zulu“";
	public const string FindCityTitle = "Stadt suchen";
	public const string FindCityPlaceholder = "Name der gesuchten Stadt";
	public const string UnknownCityTitle = "Unbekannte Stadt";

	public const string ResourceErrorTitle = "Fehler bei den Spieldaten";
	public const string EngineErrorTitle = "Fehler im Spielkern";
	public const string EngineError =
		"Im OpenCivOne-Spielkern ist ein Fehler aufgetreten.";
	public const string ExceptionLogLocation = "Fehlerprotokoll:";
	public const string ExceptionLogError =
		"Exception.log konnte nicht geschrieben werden. Fehler beim Öffnen " +
		"der Datei: ";

	public const string ExitTitle = "Spiel beenden";
	public const string ExitQuestion =
		"Möchtest du Project1991 Classic wirklich beenden?\n" +
		"Das aktuelle Spiel wird dabei nicht automatisch gespeichert.";

	public const string ZoneOfControlMovementBlocked =
		"Bewegung blockiert: Start- und Zielfeld liegen jeweils neben " +
		"gegnerischen Einheiten (Kontrollzone).";
	public const string LandUnitNeedsTransport =
		"Bewegung blockiert: Eine Landeinheit ben\u00f6tigt hier ein " +
		"eigenes Transportschiff mit freiem Platz.";
	public const string NavalUnitNeedsWater =
		"Bewegung blockiert: Diese Seeeinheit kann nur Wasser oder eine " +
		"eigene beziehungsweise unbesetzte K\u00fcstenstadt betreten.";

	public static string CityNotFound(string cityName)
	{
		return $"Die Stadt „{cityName}“ wurde nicht gefunden.";
	}
}
