namespace OpenCivOne.Input;

public readonly record struct ClassicKeyTranslation(
	bool Handled,
	ClassicKeyAction Action,
	int Value = 0);
