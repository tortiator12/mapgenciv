namespace OpenCivOne.Platform;

/// <summary>
/// Platform-owned dialogs required by the reconstructed game loop.
/// Implementations may use desktop windows, an iPad single-view host, or a
/// deterministic test double without changing Classic gameplay code.
/// </summary>
public interface IClassicGameHost
{
	string? ShowTextInput(
		string title,
		string? placeholderText,
		string? defaultValue,
		int maxTextLength,
		bool allowEmptyText);

	void ShowInformation(string text, string title);

	bool ShowConfirmation(string text, string title)
	{
		ShowInformation(text, title);
		return false;
	}

	/// <summary>
	/// Shows short, non-modal feedback without interrupting the game loop.
	/// Hosts that do not have a visual status surface may ignore it.
	/// </summary>
	void ShowTransientStatus(string text)
	{
	}
}
