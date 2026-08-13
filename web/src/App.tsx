import { Route, Routes } from 'react-router-dom'
import { Layout } from './components/Layout'
import { FilterProvider } from './context/FilterContext'
import { SearchMapView } from './views/SearchMapView'
import { JurisdictionSummaryView } from './views/JurisdictionSummaryView'
import { DistrictExposureView } from './views/DistrictExposureView'
import { RankedMunicipalitiesView } from './views/RankedMunicipalitiesView'
import { MethodologyView } from './views/MethodologyView'

export default function App() {
  return (
    <FilterProvider>
      <Routes>
        <Route element={<Layout />}>
          <Route index element={<SearchMapView />} />
          <Route path="summary" element={<JurisdictionSummaryView />} />
          <Route path="exposure" element={<DistrictExposureView />} />
          <Route path="ranked" element={<RankedMunicipalitiesView />} />
          <Route path="methodology" element={<MethodologyView />} />
        </Route>
      </Routes>
    </FilterProvider>
  )
}
