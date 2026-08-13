import { useContext } from 'react'
import { FilterContext, type FilterContextValue } from './filterTypes'

export function useFilters(): FilterContextValue {
  const ctx = useContext(FilterContext)
  if (!ctx) throw new Error('useFilters must be used within FilterProvider')
  return ctx
}
