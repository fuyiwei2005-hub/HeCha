import { useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Detection, RecordFilters, RecordPage, searchDetections } from '../api'
import { recordsKey } from './useRecords'
export function useRecordPage(filters: RecordFilters, onError: (error: unknown) => void) {
  const client = useQueryClient(), key = [...recordsKey, 'page', filters]
  const query = useQuery({queryKey: key, queryFn: ({signal}) => searchDetections(filters,signal),
    refetchInterval: q => q.state.data?.items.some(item => ['queued','processing'].includes(item.status) || ['queued','processing'].includes(item.analysis_status)) ? 2500 : false})
  useEffect(() => {if (query.error) onError(query.error)}, [query.error,onError])
  function update(item: Detection) {
    client.setQueryData<RecordPage>(key, page => page ? {...page, items: page.items.map(row => row.id === item.id ? item : row)} : page)
    void client.invalidateQueries({queryKey: recordsKey})
    void client.invalidateQueries({queryKey: ['statistics']})
  }
  function remove(id: string) {
    client.setQueryData<RecordPage>(key, page => page ? {...page, total: Math.max(0,page.total-1),items: page.items.filter(row => row.id !== id)} : page)
    void client.invalidateQueries({queryKey: recordsKey})
    void client.invalidateQueries({queryKey: ['statistics']})
  }
  return {...query, items: query.data?.items || [], total: query.data?.total || 0, update, remove}
}
