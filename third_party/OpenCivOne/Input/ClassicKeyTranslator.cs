namespace OpenCivOne.Input;

/// <summary>
/// Preserves the DOS keyboard codes and desktop-only diagnostic actions used
/// by the imported OpenCivOne runtime without depending on a UI framework.
/// </summary>
public static class ClassicKeyTranslator
{
	public static ClassicKeyTranslation Translate(
		ClassicHostKey key,
		ClassicKeyModifiers modifiers,
		char? symbol = null)
	{
		if (modifiers == ClassicKeyModifiers.None)
		{
			int? code = key switch
			{
				ClassicHostKey.Enter => 0x0d,
				ClassicHostKey.Escape => 0x1b,
				ClassicHostKey.F1 => 0x3b00,
				ClassicHostKey.F2 => 0x3c00,
				ClassicHostKey.F3 => 0x3d00,
				ClassicHostKey.F4 => 0x3e00,
				ClassicHostKey.F5 => 0x3f00,
				ClassicHostKey.F6 => 0x4000,
				ClassicHostKey.F7 => 0x4100,
				ClassicHostKey.F8 => 0x4200,
				ClassicHostKey.F9 => 0x4300,
				ClassicHostKey.F10 => 0x4400,
				ClassicHostKey.Down or ClassicHostKey.NumPad2 => 0x5000,
				ClassicHostKey.Left or ClassicHostKey.NumPad4 => 0x4b00,
				ClassicHostKey.Right or ClassicHostKey.NumPad6 => 0x4d00,
				ClassicHostKey.Up or ClassicHostKey.NumPad8 => 0x4800,
				ClassicHostKey.Home or ClassicHostKey.NumPad7 => 0x4700,
				ClassicHostKey.End or ClassicHostKey.NumPad1 => 0x4f00,
				ClassicHostKey.PageUp or ClassicHostKey.NumPad9 => 0x4900,
				ClassicHostKey.PageDown or ClassicHostKey.NumPad3 => 0x5100,
				_ => symbol,
			};

			return code.HasValue
				? new ClassicKeyTranslation(true, ClassicKeyAction.EnqueueDosCode, code.Value)
				: new ClassicKeyTranslation(false, ClassicKeyAction.None);
		}

		if ((modifiers & ClassicKeyModifiers.Shift) != 0)
		{
			int? code = key switch
			{
				ClassicHostKey.Down => 0x5032,
				ClassicHostKey.Left => 0x4b34,
				ClassicHostKey.Right => 0x4d36,
				ClassicHostKey.Up => 0x4838,
				ClassicHostKey.Home => 0x4737,
				ClassicHostKey.End => 0x4f31,
				ClassicHostKey.PageUp => 0x4939,
				ClassicHostKey.PageDown => 0x5133,
				_ => symbol,
			};

			return code.HasValue
				? new ClassicKeyTranslation(true, ClassicKeyAction.EnqueueDosCode, code.Value)
				: new ClassicKeyTranslation(false, ClassicKeyAction.None);
		}

		if ((modifiers & ClassicKeyModifiers.Alt) != 0)
		{
			return key switch
			{
				ClassicHostKey.Digit1 => ToggleScreen(0),
				ClassicHostKey.Digit2 => ToggleScreen(1),
				ClassicHostKey.Digit3 => ToggleScreen(2),
				ClassicHostKey.Digit4 => ToggleScreen(3),
				ClassicHostKey.A => Enqueue(0x1e00),
				ClassicHostKey.C => Enqueue(0x2e00),
				ClassicHostKey.D => Enqueue(0x2000),
				ClassicHostKey.G => Enqueue(0x2200),
				ClassicHostKey.H => Enqueue(0x2300),
				ClassicHostKey.M => Enqueue(0x3200),
				ClassicHostKey.O => Enqueue(0x1800),
				ClassicHostKey.P => new ClassicKeyTranslation(true, ClassicKeyAction.TogglePause),
				ClassicHostKey.Q => Enqueue(0x1000),
				ClassicHostKey.R => Enqueue(0x1300),
				ClassicHostKey.V => Enqueue(0x2f00),
				ClassicHostKey.W => Enqueue(0x1100),
				_ => new ClassicKeyTranslation(false, ClassicKeyAction.None),
			};
		}

		// The original desktop handler consumed Control/Meta-only keys without
		// placing a DOS key in the queue. Preserve that behavior.
		return new ClassicKeyTranslation(true, ClassicKeyAction.None);
	}

	private static ClassicKeyTranslation Enqueue(int code) =>
		new(true, ClassicKeyAction.EnqueueDosCode, code);

	private static ClassicKeyTranslation ToggleScreen(int index) =>
		new(true, ClassicKeyAction.ToggleScreen, index);
}
