# Wunderfilme – Storyboards, Runde 1: die 6 fehlenden Wunder

Stand: 24.09.2026 · Zur Abnahme – nach Freigabe wird gerendert.
Weg A: rein prozedural (Blender/Cycles), Stil an die vorhandenen Civ1-Wunderfilme angepasst.

---

## Regeln für alle Filme

**Technik**
- 20,0 s, 24 fps (480 Bilder), 1280×720.
- Kein Text im Bild: Titel, „WELTWUNDER VOLLENDET“, Jahr und Effekt blendet das Spiel selbst ein.
- Ton: Musik der jeweiligen Epoche und Geräusche, Lautheit wie die vorhandenen Filme (≈ −24 dB Mittelwert).
- Lieferung: MP4 (zum Hochskalieren), OGV (direkt fürs Spiel) und je eine Zeile in `scripts/WonderFilms.cs`.

**Aufbau (wie die vorhandenen Filme, nur länger)**
Anlieferung mit Leben → Bau im Zeitraffer → Handwerk im Detail → Vollendung → Szene aus der Epoche.

**Kein Morphing, physikalisch korrekt**
- Innerhalb einer Einstellung verändert sich nichts fließend. Bauwerke wachsen nur durch echte Einzelteile (Block, Balken, Platte, Planke). Gerüste werden Stück für Stück auf- und wieder abgebaut.
- Zeit vergeht nur sichtbar: Sonne und Schatten wandern, Wolken ziehen, Menschen springen von Ort zu Ort (Zeitraffer), Tag und Nacht wechseln.
- Übergänge: harte Schnitte oder kurze Blenden (≤ 0,4 s), und nur zwischen deutlich verschiedenen Bildern. Nie dasselbe Motiv ineinander blenden, das wirkt wie Morphing.
- Jede Last hängt an einem Seil, das an einem Kran endet. Menschen stehen auf Boden, Gerüst oder Deck. Wasser fließt bergab. Schatten passen zum Sonnenstand.
- Das Bauwerk ist von der ersten bis zur letzten Einstellung dasselbe Modell. Architektur- oder Gebäudewechsel sind ausgeschlossen, weil alles aus einer 3D-Szene kommt.

**Stil**
- Hell, warm und malerisch wie die vorhandenen Filme: blauer Himmel mit Quellwolken, goldenes Licht, am Ende Abend- oder Nachtstimmung mit warmen Lichtern.
- Keine Tuschelinien wie beim ersten Leuchtturm-Film. Stattdessen ein weicher Malfilter und viele Details.
- Menschen im Mittel- und Fernbereich oder als Silhouette. Nahaufnahmen von Gesichtern und Händen kann die 3D-Pipeline nicht überzeugend; deshalb sind alle Figurenszenen so geplant, dass das nicht nötig ist.

---

## 04 – Der Leuchtturm (Pharos von Alexandria)

`wunderfilm_04_lighthouse` · ca. 280–247 v. Chr. · Grundlage: Rekonstruktion nach Thiersch (1909). Die Szene ist schon gebaut, deshalb als Stiltest zuerst.

- **S1 · 0,0–3,0 s · Kai auf Pharos, Morgen, Halbtotale, langsame Seitfahrt**
  Lastkähne legen an, ein Schwenkkran hebt Kalksteinblöcke an Land, Ochsenkarren fahren ab. Dahinter die leere Landspitze mit Absteckpflöcken und Schnüren. Möwen.
- **S2 · 3,0–11,0 s · Zeitraffer, Totale, langsame Kreisfahrt um die Baustelle**
  Stufensockel → quadratisches Untergeschoss Lage für Lage (Fenster, Tor) → Achteck → Rundbau. Das Gerüst klettert mit und wird unten wieder abgebaut, Derrick-Krane heben Blöcke, Arbeiter stehen auf der Mauerkrone. Die Sonne wandert, eine kurze Nacht mit Fackeln, Wolkenschatten ziehen übers Wasser.
- **S3 · 11,0–13,5 s · Nah an der Laterne, goldene Stunde**
  Ein hoher Derrick hievt die Bronzestatue des Zeus Soter auf die Kuppel, Arbeiter führen sie an Leinen. An den Ecken des ersten Gesimses stehen schon die Tritonen.
- **S4 · 13,5–16,0 s · Totale, Abenddämmerung**
  Alle Gerüste sind abgebaut. Das Feuer in der Laterne wird entzündet, der erste Lichtschein fällt aufs Meer.
- **S5 · 16,0–20,0 s · Szene aus der Epoche, Nacht**
  Ein Handelsschiff mit Rahsegel läuft, vom Leuchtfeuer geführt, in den Großen Hafen ein. Matrosen reffen das Segel, eine Laterne brennt am Heck. Die Kamera steht knapp über dem Wasser: das Schiff im Vordergrund, der Leuchtturm dahinter, am Horizont die Lichter Alexandrias.
- **Ton:** Leier- und Aulos-artige Melodie, Rahmentrommel beim Bau, Meer und Wind; beim Entzünden ein Aufbrausen, am Schluss Wellen, knarrendes Holz und Rufe der Matrosen.
- **Physik-Check:** Die Statue hängt an einem Kran, der hoch genug ist (die Spitze des Auslegers liegt über der Statue). Das Feuer ist ein offenes Feuer ohne drehenden Strahl wie bei einem modernen Leuchtturm.

---

## 03 – Koloss von Rhodos

`wunderfilm_03_colossus` · ca. 292–280 v. Chr. · Bildhauer Chares von Lindos.

**Grundlage:**
- Nach Philon von Byzanz: Bronzehaut über einem Eisengerüst, innen Steinfüllung, gebaut Abschnitt für Abschnitt innerhalb eines mitwachsenden Erdhügels.
- Etwa 33 m hoch auf einem weißen Marmorsockel.
- Bezahlt aus dem Verkauf der zurückgelassenen Belagerungsmaschinen des Demetrios.

**Bewusste Korrektur:** Der Koloss stand **nicht** breitbeinig über der Hafeneinfahrt; das ist ein mittelalterlicher Mythos und statisch unmöglich. Bei uns steht er auf einer Mole am Hafeneingang: aufrechte Figur, Beine eng, ein Mantel fällt als dritte Stütze bis zum Sockel. Dazu eine Strahlenkrone; die rechte Hand beschattet die Augen, der Blick geht aufs Meer.

- **S1 · 0,0–3,0 s · Hafen von Rhodos, Morgen**
  Schiffe entladen Bronzebarren und Eisenstangen. Am Kai liegen zerlegte Belagerungstürme als Holz- und Eisenlager, Ochsenkarren fahren, Schmiedefeuer rauchen.
- **S2 · 3,0–8,0 s · Zeitraffer, Totale**
  Der Marmorsockel entsteht, darauf das Eisengerüst der Beine mit Steinfüllung. Um die Figur wird Schicht für Schicht ein Erdhügel mit spiralförmiger Rampe aufgeschüttet; nur die jeweils oberste Partie ragt heraus. Bronzeplatten werden angesetzt und vernietet. Die Sonne wandert, ein Tag-Nacht-Wechsel mit Feuerschein.
- **S3 · 8,0–11,5 s · Halbnah auf der Hügelkuppe**
  Gießerei unter freiem Himmel: Schmelzöfen, Blasebälge, Glut. Arbeiter setzen Platten an Brust und Kopf, Rauch weht im Wind.
- **S4 · 11,5–15,0 s · Totale, Enthüllung im Zeitraffer**
  Der Erdhügel wird Lage für Lage mit Körben und Karren abgetragen. Die Figur erscheint von oben nach unten, die Bronze glänzt in der Sonne.
- **S5 · 15,0–20,0 s · Szene aus der Epoche, Sonnenuntergang**
  Eine Handelsgaleere rudert in den Hafen und fährt am Koloss vorbei. Am Kai stehen Menschen, am Sockel brennt ein Opferfeuer, Möwen fliegen.
- **Ton:** Hämmern auf Bronze, Blasebälge und Glut, griechisch anmutende Melodie; am Schluss Ruderschlag und Hafenlärm.
- **Physik-Check:** Die Figur steht auf drei Stützen (zwei Beine und Mantel). Der Erdhügel verdeckt beim Bau den unteren Teil, genau wie in Philons Bericht. Die Enthüllung geschieht durch Abtragen, nicht durch Einblenden.

---

## 10 – Kopernikus' Observatorium

`wunderfilm_10_copernicus` · ca. 1512–1543.

**Grundlage:**
- Frombork (Frauenburg) am Frischen Haff, Domhügel mit Wehrmauer und Türmen.
- Kopernikus beobachtete von einer Plattform aus mit selbstgebauten Holzinstrumenten: Triquetrum, Quadrant und Armillarsphäre (beschrieben in *De revolutionibus*, 1543).
- Spielgerecht zeigt der Film den Bau eines Backstein-Beobachtungsturms an der Domburg (angelehnt an den „Kopernikusturm“), mit Plattform und Instrumenten.

- **S1 · 0,0–3,0 s · Domhügel über dem Haff, Morgen, Totale**
  Ziegelöfen rauchen, Karren mit Backsteinen fahren, Handwerker arbeiten, Domherren in dunklen Gewändern gehen über den Hof.
- **S2 · 3,0–9,0 s · Zeitraffer**
  Der Backsteinturm wächst Lage für Lage im gotischen Verband. Ein Holzgerüst mit Leitern und ein Tretradkran stehen auf der Mauer. Dann kommen Zinnen, der Dachstuhl und eine flache Plattform mit Brüstung. Sonne und Wolkenschatten ziehen.
- **S3 · 9,0–12,5 s · Werkstatt, Innenraum mit schrägem Fensterlicht**
  Ein Zimmermann und Kopernikus (von hinten bzw. im Halbprofil) bauen das Triquetrum aus Holz, dazu Messingskalen, Kerzen und Pergamente mit Kreisbahnen.
- **S4 · 12,5–15,5 s · Plattform bei Sonnenuntergang**
  Die Instrumente werden aufgestellt, die Armillarsphäre glänzt im letzten Licht.
- **S5 · 15,5–20,0 s · Szene aus der Epoche, Nacht**
  Kopernikus peilt als Silhouette mit dem Triquetrum den Mond an. Im Zeitraffer drehen sich die Sterne um den Polarstern, Mondlicht liegt auf dem Haff, im Vordergrund das Domdach. Der Film endet auf dem Sternenhimmel.
- **Ton:** Renaissance-Laute und Blockflöte, Maurerkellen und Glocken; nachts Stille, Wind und ein leiser Chor.
- **Physik-Check:** Die Sterne drehen sich um den richtigen Pol; Frombork liegt auf etwa 54° Nord, so hoch steht der Polarstern. Mondlicht und Schatten kommen aus derselben Richtung.

---

## 13 – J. S. Bachs Kathedrale

`wunderfilm_13_bach` · 1726–1743.

**Grundlage:**
- Angelehnt an die Dresdner Frauenkirche (Baumeister George Bähr, 1726–1743).
- Bach spielte am 1.12.1736 die neue Silbermann-Orgel dieser Kirche.
- Der Sandstein kam per Elbkahn aus der Sächsischen Schweiz.
- Das Spiel nennt es „Kathedrale“, historisch ist es eine Kirche.

- **S1 · 0,0–3,0 s · Elbufer in Dresden, Morgen**
  Elbkähne mit Sandsteinquadern legen an, ein Tretradkran steht am Ufer, Pferdefuhrwerke fahren, Steinmetze behauen Blöcke.
- **S2 · 3,0–10,0 s · Zeitraffer, Totale**
  Grundmauern, acht Pfeiler, Außenwände mit Fenstern, Emporen. Dann wächst die steinerne Kuppel Ring für Ring über einem hölzernen Lehrgerüst, zuletzt die Laterne. Gerüste und Tretradkrane wandern mit, ein bis zwei Tag-Nacht-Wechsel.
- **S3 · 10,0–13,0 s · Innenraum**
  Orgelbauer setzen Pfeifen ins Gehäuse der Silbermann-Orgel, Vergolder arbeiten am Altar, schräges Licht fällt durch die hohen Fenster.
- **S4 · 13,0–15,5 s · Totale, Abend**
  Gerüste und Lehrgerüst sind abgebaut, die Kirche ist fertig. Glocken läuten, Menschen strömen hinein.
- **S5 · 15,5–20,0 s · Szene aus der Epoche, Kerzenlicht**
  Blick von der Empore: Bach an der Orgel, von hinten gesehen (Perücke, Rock), Chor und Gemeinde auf den Emporen, Kerzenlüster.
- **Ton:** Hämmern und Glocken beim Bau. Am Schluss Orgelmusik, und zwar ein Bach-Choral (gemeinfrei), den ich mit einem Orgelklang synthetisiere.
- **Physik-Check:** Die Kuppel ruht beim Bau auf dem Lehrgerüst, und das Lehrgerüst wird erst entfernt, wenn der Ring geschlossen ist. Die Krane stehen auf fertigen Mauerteilen oder auf dem Boden.

---

## 08 – Magellans Expedition

`wunderfilm_08_magellan` · 1519–1522.

**Grundlage:**
- Fünf Schiffe: Trinidad, San Antonio, Concepción, Victoria, Santiago.
- Sie wurden 1519 in Sevilla am Guadalquivir überholt und ausgerüstet und liefen am 20.9.1519 in Sanlúcar aus.
- Nur die Victoria kehrte am 6.9.1522 unter Elcano mit 18 Mann zurück.
- Das „Bauwerk“ ist hier die Ausrüstung der Flotte.

- **S1 · 0,0–3,0 s · Kai in Sevilla, Morgen, Torre del Oro im Hintergrund**
  Fässer, Säcke, Kanonen und Tauwerk auf Karren, dazu Händler und Soldaten.
- **S2 · 3,0–9,0 s · Zeitraffer**
  Die Victoria liegt zum Überholen gekrängt am Ufer. Der Rumpf wird abgeschabt, Planken werden ersetzt und mit Pech kalfatert (Kessel über Feuer). Dann wird sie aufgerichtet, die Masten werden mit einem Mastkran gesetzt, Takelage und Segel angeschlagen. Daneben liegen die anderen vier Schiffe in verschiedenen Stadien der Ausrüstung.
- **S3 · 9,0–12,0 s · Halbnah an Deck**
  Fässer werden über Taljen in den Laderaum gehievt, Kompass und Astrolabium kommen an Bord, die Flagge wird gesetzt.
- **S4 · 12,0–15,0 s · Totale, Aufbruch**
  Alle fünf Schiffe fahren mit gesetzten Segeln im Zeitraffer flussabwärts, am Ufer winken Menschen.
- **S5 · 15,0–20,0 s · Szene aus der Epoche: die Heimkehr 1522**
  Die Victoria läuft allein bei Sonnenaufgang in Sanlúcar ein, mit zerschlissenen, geflickten Segeln. Menschen stehen am Strand, ein Kirchturm ist zu sehen, ein Salutschuss raucht.
- **Ton:** Renaissance-Trommel und Schalmei, Hämmern, Taue und Möwen; am Schluss Glocken und ein leiser Chor.
- **Physik-Check:** Das Schiff liegt beim Überholen auf der Seite und wird mit Taljen und Winden wieder aufgerichtet. Die Segel stehen passend zum Wind, der Rauch weht in dieselbe Richtung.

---

## 14 – Darwins Reise

`wunderfilm_14_darwin` · 1831–1836.

**Grundlage:**
- Die HMS Beagle (eine Brigg der Cherokee-Klasse) wurde 1831 in Devonport umgebaut: erhöhtes Oberdeck, zusätzlicher Besanmast (Bark-Takelung), Kupferbeschlag, 22 Chronometer an Bord.
- Abfahrt Plymouth 27.12.1831, auf den Galápagos im September und Oktober 1835.
- Das „Bauwerk“ ist der Umbau des Schiffs.

- **S1 · 0,0–3,0 s · Werft Devonport, Morgen**
  Trockendock, Holzstapel, gestapelte Kupferplatten, ein Seiler, Marinesoldaten.
- **S2 · 3,0–9,0 s · Zeitraffer im Dock**
  Spanten und Planken erhöhen das Oberdeck. Kupferplatten werden Reihe für Reihe von unten nach oben am Rumpf angebracht und glänzen. Der Besanmast wird gesetzt, die Takelung folgt. Dann wird das Dock geflutet und das Schiff schwimmt auf.
- **S3 · 9,0–12,0 s · Halbnah an Deck**
  Chronometerkisten, Instrumente und Fässer werden an Bord gebracht. Darwin (junger Mann, Halbtotale) kommt mit Kisten voller Gläser und mit Netzen an Bord.
- **S4 · 12,0–15,0 s · Totale, Ausfahrt aus dem Plymouth Sound**
  Die Segel sind gesetzt, frischer Wind, klares Winterlicht.
- **S5 · 15,0–20,0 s · Szene aus der Epoche: Galápagos, goldene Stunde**
  Die Beagle liegt in einer Bucht vor Anker, ein Beiboot liegt am schwarzen Lavastrand. Meerechsen sonnen sich auf den Felsen, eine Riesenschildkröte zieht vorbei. Darwin kniet mit Notizbuch, Finken fliegen auf.
- **Ton:** Hämmern und Sägen in der Werft, Möwen, Streicher; am Schluss Brandung und Vogelrufe.
- **Physik-Check:** Das Schiff schwimmt erst auf, wenn das Dock geflutet ist, und die Wasserlinie passt zum Tiefgang. Die Tiere haben realistische Größe; die Schildkröte bewegt sich langsam.

---

## Reihenfolge und Aufwand

1. **Leuchtturm:** Szene steht bereits, dient als Stiltest.
2. **Koloss**
3. **Kopernikus**
4. **Bach**
5. **Magellan**
6. **Darwin**

Magellan und Darwin kommen zuletzt, weil Schiffe mit Takelage der aufwendigste Teil sind.

Pro Film etwa einen halben Tag: Szene bauen, Vorschau, deine Abnahme, dann das Rendern (720p, 20 s, etwa 1–1,5 h).

## Kritische Punkte

- **Look:** Das Ergebnis wird malerisch, aber nicht identisch mit deinen KI-Filmen. Die Figuren sind einfacher und die Texturen weniger „gemalt“. Wenn dich der Leuchtturm-Stiltest überzeugt, lohnt es sich, später auch die fehlerhaften 15 Filme so neu zu machen, damit alle Filme gleich aussehen.
- **Menschen:** In meiner Pipeline sind das einfache Figuren. Deshalb gibt es keine Nahaufnahmen von Gesichtern. Bach, Kopernikus und Darwin erscheinen von hinten, als Silhouette oder in der Halbtotale.
- **Geschichte:** Koloss, Kopernikus-Turm und Bach-Kirche sind begründete Rekonstruktionen bzw. Anlehnungen, keine gesicherten Abbilder. Wo das Spiel Fiktion ist (Bachs „Kathedrale“), habe ich das historisch passendste Vorbild gewählt.
