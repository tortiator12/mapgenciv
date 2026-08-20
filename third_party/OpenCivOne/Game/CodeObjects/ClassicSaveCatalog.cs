using OpenCivOne.Localization;
using System.Text;

namespace OpenCivOne;

public readonly record struct ClassicSaveCatalogEntry(
	string FileName,
	ClassicSaveSlotInfo Slot,
	DateTime LastWriteTimeUtc,
	bool IsAutoSave);

public enum ClassicSaveCatalogOptionKind
{
	Save,
	PreviousPage,
	NextPage,
	Unavailable,
}

public readonly record struct ClassicSaveCatalogOption(
	ClassicSaveCatalogOptionKind Kind,
	string? FileName);

public readonly record struct ClassicSaveCatalogPagePlan(
	string Text,
	int DisabledOptionsMask,
	int DefaultOptionIndex,
	int PageIndex,
	int PageCount,
	IReadOnlyList<ClassicSaveCatalogOption> Options)
{
	public const int DefaultPageSize = 8;

	public static ClassicSaveCatalogPagePlan Create(
		IReadOnlyList<ClassicSaveCatalogEntry> entries,
		int requestedPageIndex,
		int pageSize = DefaultPageSize)
	{
		ArgumentNullException.ThrowIfNull(entries);
		if (pageSize < 1 || pageSize > 28)
		{
			throw new ArgumentOutOfRangeException(nameof(pageSize));
		}

		int pageCount = Math.Max(
			1,
			(entries.Count + pageSize - 1) / pageSize);
		int pageIndex = Math.Clamp(
			requestedPageIndex,
			0,
			pageCount - 1);
		int firstEntryIndex = pageIndex * pageSize;
		int entryCount = Math.Min(
			pageSize,
			entries.Count - firstEntryIndex);
		StringBuilder text = new();
		text.Append('\x008c');
		text.Append(
			ClassicGameText.Current.Format(
				ClassicGameTextKey.LoadGameCatalogTitle,
				pageIndex + 1,
				pageCount));
		text.Append('\n');

		List<ClassicSaveCatalogOption> options = new();
		int disabledOptionsMask = 0;
		int defaultOptionIndex = -1;

		if (entryCount == 0)
		{
			options.Add(
				new ClassicSaveCatalogOption(
					ClassicSaveCatalogOptionKind.Unavailable,
					null));
			text.Append(
				ClassicGameText.Current[
					ClassicGameTextKey.LoadGameCatalogEmpty]);
			disabledOptionsMask = 1;
		}
		else
		{
			for (int offset = 0; offset < entryCount; offset++)
			{
				ClassicSaveCatalogEntry entry =
					entries[firstEntryIndex + offset];
				int optionIndex = options.Count;
				options.Add(
					new ClassicSaveCatalogOption(
						ClassicSaveCatalogOptionKind.Save,
						entry.FileName));
				text.Append(entry.Slot.DisplayText);
				if (!entry.Slot.CanLoad)
				{
					disabledOptionsMask |= 1 << optionIndex;
				}
				else if (defaultOptionIndex < 0)
				{
					defaultOptionIndex = optionIndex;
				}
			}
		}

		if (pageIndex > 0)
		{
			options.Add(
				new ClassicSaveCatalogOption(
					ClassicSaveCatalogOptionKind.PreviousPage,
					null));
			text.Append(
				ClassicGameText.Current[
					ClassicGameTextKey.LoadGameCatalogPreviousPage]);
		}

		if (pageIndex + 1 < pageCount)
		{
			options.Add(
				new ClassicSaveCatalogOption(
					ClassicSaveCatalogOptionKind.NextPage,
					null));
			text.Append(
				ClassicGameText.Current[
					ClassicGameTextKey.LoadGameCatalogNextPage]);
		}

		if (defaultOptionIndex < 0)
		{
			defaultOptionIndex =
				options.FindIndex(
					option =>
						option.Kind is
							ClassicSaveCatalogOptionKind.PreviousPage or
							ClassicSaveCatalogOptionKind.NextPage);
		}

		return new ClassicSaveCatalogPagePlan(
			text.ToString(),
			disabledOptionsMask,
			defaultOptionIndex,
			pageIndex,
			pageCount,
			options);
	}
}
