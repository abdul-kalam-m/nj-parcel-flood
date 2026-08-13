import { BAND_COLORS, BAND_LABELS } from '../lib/bands'
import type { Band } from '../types'

// §4 (data sources), §5 (methodology/scoring, LOCKED), §15 (glossary) of
// OPERATING_GUIDE.md, reproduced/paraphrased for a general audience -- not
// invented. Numbers (weights, bands, thresholds) are copied verbatim from
// §5.3/§5.4 since those are locked and must match what 05_score.py actually
// computes.
const DATA_SOURCES = [
  { code: 'P1', dataset: 'Parcel geometry + MOD-IV attributes', source: 'NJGIN/NJOGIS "Parcels and MOD-IV Composite of NJ"', role: 'The parcel master (§5.1): one row per parcel, identifiers, class, assessed value.' },
  { code: 'P2', dataset: 'Raw MOD-IV tax list', source: 'NJ Treasury / NJGIN MOD-IV products', role: 'Enrichment and validation of P1.' },
  { code: 'P3', dataset: 'Current flood hazard', source: 'FEMA National Flood Hazard Layer (NFHL) for NJ', role: 'Current-risk overlap: SFHA zones A/AE/AO/AH/VE (1% annual chance), shaded X (0.2%).' },
  { code: 'P4', dataset: 'Future flood indicators', source: 'NJDEP climate-adjusted / sea-level-rise inundation layers', role: 'Future-risk overlap where coverage exists; inland parcels outside coverage are marked "n/a here", never "no future risk".' },
  { code: 'P5', dataset: 'Flood design/profile context', source: 'NJGIN flood design-flood / flood profile layers', role: 'Contextual only, not scored.' },
  { code: 'P6', dataset: 'NFIP loss evidence', source: 'OpenFEMA FIMA NFIP Redacted Claims', role: 'Tract-level claims density feeding C_loss (never shown below tract level, §5.6).' },
  { code: 'P7', dataset: 'Boundaries', source: 'Census TIGER counties/municipalities/tracts', role: 'County and municipality choropleth geometry.' },
  { code: 'P8', dataset: 'Address geocoding', source: "NJ's own ArcGIS geocoder (geo.nj.gov)", role: 'Powers the statewide address search in the search bar.' },
  { code: 'P9', dataset: 'Basemap', source: 'OpenFreeMap vector tiles', role: 'Background map tiles, no API key required.' },
]

const GLOSSARY: { term: string; def: string }[] = [
  { term: 'MOD-IV', def: "NJ's statewide property tax assessment system — source of property class codes and assessed values." },
  { term: 'PAMS PIN', def: 'Statewide parcel identifier that links parcel geometry to its MOD-IV record.' },
  { term: 'Block / Lot / Qual', def: 'Municipal tax identifiers; together with municipality they form a fallback key when a PIN is missing.' },
  { term: 'NFHL / SFHA', def: "FEMA's National Flood Hazard Layer / Special Flood Hazard Area — the zone with a 1% annual chance of flooding. \"Shaded X\" is the lower-risk 0.2%-annual-chance zone." },
  { term: 'NJGIN / NJOGIS', def: "New Jersey's geospatial data infrastructure and geographic information office — source for parcel, boundary, and flood-layer data." },
  { term: 'OpenFEMA redacted claims', def: 'Public NFIP flood insurance claims records, with fields masked to protect privacy; aggregated to census tract before use here.' },
  { term: 'PMTiles', def: 'A single-file map tile archive served directly over HTTP range requests — no tile server needed.' },
  { term: 'Presence floor', def: 'A minimum credit given to any parcel with nonzero flood overlap, so a barely-touched parcel never scores misleadingly close to zero (§5.3).' },
  { term: 'Ratable base', def: "A municipality's total assessed property value." },
  { term: 'Lens (current / future / either)', def: 'Which risk window a view is filtered to: today\'s flood zones, projected future indicators, or a parcel flagged by either.' },
  { term: 'Band', def: 'The 5-step risk category a score falls into: None, Low, Moderate, High, Severe (see thresholds below).' },
  { term: 'Class group', def: "A parcel's MOD-IV property class, rolled up into one of 7 reporting categories (see table below)." },
]

const CLASS_CROSSWALK: [string, string][] = [
  ['Residential', '2 (residential), 4C (apartments)'],
  ['Commercial', '4A'],
  ['Industrial', '4B'],
  ['Farm/Agricultural', '3A, 3B'],
  ['Vacant', '1'],
  ['Public/Institutional/Exempt', '15A–15F'],
  ['Other (rail/utility/misc)', '5A, 5B, 6A, 6B, and any unmapped code'],
]

const BANDS_TABLE: [Band, string][] = [
  ['none', 'score = 0'],
  ['low', '1–24'],
  ['moderate', '25–49'],
  ['high', '50–74'],
  ['severe', '75–100'],
]

function Section({ id, title, children }: { id: string; title: string; children: React.ReactNode }) {
  return (
    <section id={id} className="mb-10 scroll-mt-24">
      <h3 className="mb-3 border-b-2 border-brand-700/20 pb-1.5 text-xl font-bold tracking-tight dark:border-brand-400/30">
        {title}
      </h3>
      {children}
    </section>
  )
}

export function MethodologyView() {
  return (
    <section>
      <h2 className="mb-1 text-2xl font-bold tracking-tight">Methodology</h2>
      <p className="mb-4 max-w-3xl text-sm text-zinc-600 dark:text-zinc-400">
        How the score, bands, and aggregates on every other page are computed, and where the
        underlying data comes from. Every figure below (weights, band cutoffs, class mapping) is
        copied from the project's locked methodology spec, not approximated.
      </p>

      <nav
        aria-label="On this page"
        className="mb-6 flex flex-wrap gap-2 text-sm"
      >
        {[
          ['#data-sources', 'Data sources'], ['#scoring', 'Composite score'], ['#classes', 'Class groups'],
          ['#aggregates', 'Aggregate figures'], ['#privacy', 'Privacy'], ['#glossary', 'Glossary'],
        ].map(([href, label]) => (
          <a
            key={href}
            href={href}
            className="rounded-full border border-brand-700/20 px-3 py-1 font-medium text-brand-700 transition-colors hover:bg-brand-50 dark:border-brand-400/30 dark:text-brand-400 dark:hover:bg-zinc-800"
          >
            {label}
          </a>
        ))}
      </nav>

      <Section id="data-sources" title="Data sources">
        <div className="overflow-hidden rounded-lg border border-zinc-200 dark:border-zinc-800">
          <div className="overflow-x-auto">
            <table className="w-full min-w-[640px] border-collapse text-sm">
              <thead>
                <tr className="border-b border-zinc-300 bg-zinc-50 text-left font-semibold dark:border-zinc-700 dark:bg-zinc-900">
                  <th scope="col" className="py-2 pl-4 pr-4">#</th>
                  <th scope="col" className="py-2 pr-4">Dataset</th>
                  <th scope="col" className="py-2 pr-4">Source</th>
                  <th scope="col" className="py-2 pr-4">Role in this dashboard</th>
                </tr>
              </thead>
              <tbody>
                {DATA_SOURCES.map((d) => (
                  <tr
                    key={d.code}
                    className="border-b border-zinc-100 align-top odd:bg-zinc-50/70 hover:bg-brand-50 last:border-b-0 dark:border-zinc-800 dark:odd:bg-zinc-900/40 dark:hover:bg-zinc-800"
                  >
                    <td className="py-1.5 pl-4 pr-4 text-zinc-400">{d.code}</td>
                    <td className="py-1.5 pr-4 font-medium">{d.dataset}</td>
                    <td className="py-1.5 pr-4 text-zinc-600 dark:text-zinc-400">{d.source}</td>
                    <td className="py-1.5 pr-4 text-zinc-600 dark:text-zinc-400">{d.role}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </Section>

      <Section id="scoring" title="Composite score (0–100) and bands">
        <p className="mb-3 max-w-3xl text-sm">
          Every parcel gets a score out of 100, built from three components, each already scaled to
          a 0–1 fraction before weighting:
        </p>
        <dl className="mb-3 grid max-w-3xl grid-cols-1 gap-3 sm:grid-cols-3">
          <div className="rounded-lg border border-zinc-200 p-3 shadow-sm transition-shadow hover:shadow-md dark:border-zinc-800 dark:shadow-none">
            <dt className="font-medium">C_cur — current risk <span className="font-normal text-zinc-400">×0.45</span></dt>
            <dd className="mt-1 text-zinc-600 dark:text-zinc-400">
              Overlap with FEMA SFHA zones today, plus a smaller credit for moderate ("shaded X")
              overlap. A presence floor means any nonzero SFHA touch scores at least 0.3 before
              weighting, not a fraction near zero.
            </dd>
          </div>
          <div className="rounded-lg border border-zinc-200 p-3 shadow-sm transition-shadow hover:shadow-md dark:border-zinc-800 dark:shadow-none">
            <dt className="font-medium">C_fut — future risk <span className="font-normal text-zinc-400">×0.30</span></dt>
            <dd className="mt-1 text-zinc-600 dark:text-zinc-400">
              Overlap with projected future flood layers. Where that data doesn't cover a parcel,
              this is estimated as half of C_cur instead, and the parcel panel says so explicitly
              rather than implying "no future risk".
            </dd>
          </div>
          <div className="rounded-lg border border-zinc-200 p-3 shadow-sm transition-shadow hover:shadow-md dark:border-zinc-800 dark:shadow-none">
            <dt className="font-medium">C_loss — claims history <span className="font-normal text-zinc-400">×0.25</span></dt>
            <dd className="mt-1 text-zinc-600 dark:text-zinc-400">
              The parcel's census tract's NFIP claims, expressed as a statewide percentile — a
              proxy for how often flood losses have actually been paid out nearby.
            </dd>
          </div>
        </dl>
        <p className="mb-3 max-w-3xl rounded-lg border-l-4 border-brand-700 bg-zinc-50 p-3 font-mono text-sm dark:border-brand-400 dark:bg-zinc-900">
          score = round(100 × (0.45·C_cur + 0.30·C_fut + 0.25·C_loss))
        </p>
        <p className="mb-2 text-sm">That score sorts into 5 bands:</p>
        <table className="w-full max-w-sm border-collapse text-sm">
          <thead>
            <tr className="border-b border-zinc-300 text-left dark:border-zinc-700">
              <th scope="col" className="py-1 pr-4">Band</th>
              <th scope="col" className="py-1 pr-4">Score range</th>
            </tr>
          </thead>
          <tbody>
            {BANDS_TABLE.map(([band, range]) => (
              <tr key={band} className="border-b border-zinc-100 dark:border-zinc-800">
                <td className="py-1 pr-4">
                  <span
                    className="mr-2 inline-block h-2.5 w-2.5 rounded-full border border-black/15 align-middle"
                    style={{ background: BAND_COLORS[band] }}
                    aria-hidden="true"
                  />
                  {BAND_LABELS[band]}
                </td>
                <td className="py-1 pr-4 tabular-nums">{range}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </Section>

      <Section id="classes" title="Class groups (MOD-IV → reporting category)">
        <p className="mb-3 max-w-3xl text-sm text-zinc-600 dark:text-zinc-400">
          Every parcel's raw MOD-IV property class code rolls up into one of 7 groups used
          throughout the filters and charts. Any code that doesn't map to one of the first six goes
          to "Other" and is logged, never silently dropped.
        </p>
        <div className="max-w-2xl overflow-hidden rounded-lg border border-zinc-200 dark:border-zinc-800">
          <table className="w-full border-collapse text-sm">
            <thead>
              <tr className="border-b border-zinc-300 bg-zinc-50 text-left font-semibold dark:border-zinc-700 dark:bg-zinc-900">
                <th scope="col" className="py-2 pl-4 pr-4">Group</th>
                <th scope="col" className="py-2 pr-4">MOD-IV classes</th>
              </tr>
            </thead>
            <tbody>
              {CLASS_CROSSWALK.map(([group, classes]) => (
                <tr
                  key={group}
                  className="border-b border-zinc-100 odd:bg-zinc-50/70 hover:bg-brand-50 last:border-b-0 dark:border-zinc-800 dark:odd:bg-zinc-900/40 dark:hover:bg-zinc-800"
                >
                  <td className="py-1.5 pl-4 pr-4">{group}</td>
                  <td className="py-1.5 pr-4 text-zinc-600 dark:text-zinc-400">{classes}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>

      <Section id="aggregates" title="Aggregate figures (summary / exposure / ranked views)">
        <ul className="max-w-3xl list-disc space-y-1.5 pl-5 text-sm">
          <li><strong>% at risk</strong> = at-risk parcel count ÷ total parcel count × 100, per geography × class group × lens.</li>
          <li><strong>Value at risk (presence-based)</strong> — the full assessed value of every at-risk parcel; this is the headline figure.</li>
          <li><strong>Value at risk (overlap-based)</strong> — the same, but each parcel's value is scaled by its flood-overlap fraction; a companion figure, not the default.</li>
          <li><strong>Value exposure %</strong> = at-risk value ÷ total value × 100.</li>
        </ul>
      </Section>

      <Section id="privacy" title="Privacy">
        <p className="max-w-3xl text-sm text-zinc-600 dark:text-zinc-400">
          Owner names, owner mailing addresses, and any "care of" fields are stripped before any
          data reaches this dashboard — they never enter a processed file, tile, export, or screen.
          NFIP claims are never shown below the census-tract level. Any source field ambiguous
          enough to potentially identify a person is excluded rather than guessed about.
        </p>
      </Section>

      <Section id="glossary" title="Glossary">
        <dl className="max-w-3xl divide-y divide-zinc-100 dark:divide-zinc-800">
          {GLOSSARY.map((g) => (
            <div
              key={g.term}
              className="grid grid-cols-1 gap-1 rounded-lg px-2 py-2 transition-colors hover:bg-brand-50 sm:grid-cols-[12rem_1fr] sm:gap-4 dark:hover:bg-zinc-900"
            >
              <dt className="font-medium">{g.term}</dt>
              <dd className="text-zinc-600 dark:text-zinc-400">{g.def}</dd>
            </div>
          ))}
        </dl>
      </Section>
    </section>
  )
}
