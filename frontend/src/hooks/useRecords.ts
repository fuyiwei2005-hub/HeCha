import { useEffect } from 'react'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { Detection, listDetections } from '../api'
export const recordsKey = ['detections'] as const
export function useRecords(onError: (error: unknown) => void, mediaType?: string) {
  const client = useQueryClient()
  const key = [...recordsKey, 'list', mediaType || 'all']
  const query = useQuery({queryKey: key, queryFn: ({signal}) => listDetections(signal,mediaType),
    refetchInterval: (q) => q.state.data?.some(item =>
      ['queued', 'processing'].includes(item.status) || ['queued', 'processing'].includes(item.analysis_status)) ? 2500 : false,
  })
  useEffect(() => { if (query.error) onError(query.error) }, [query.error, onError])
  function update(item: Detection) {
    client.setQueryData<Detection[]>(key, rows => [item, ...(rows || []).filter(row => row.id !== item.id)])
    void client.invalidateQueries({queryKey: recordsKey})
    void client.invalidateQueries({queryKey: ['statistics']})
  }
  function remove(id: string) {
    client.setQueryData<Detection[]>(key, rows => (rows || []).filter(row => row.id !== id))
    void client.invalidateQueries({queryKey: recordsKey})
    void client.invalidateQueries({queryKey: ['statistics']})
  }
  return {...query, items: query.data || [], update, remove}
}
