import {
  useMutation,
  type UseMutationOptions,
  useQuery,
  type UseQueryOptions,
  useQueryClient,
  type QueryKey,
  type MutationFunctionContext,
} from "@tanstack/react-query";

/**
 * Thin wrapper around useQuery. The fetcher signature is `() => Promise<T>`.
 *
 * Usage:
 *   const tenants = useTypedQuery(
 *     queryKeys.tenants.list(),
 *     () => api.tenants.list(),
 *   );
 */
export function useTypedQuery<TData, TError = Error>(
  queryKey: QueryKey,
  queryFn: () => Promise<TData>,
  options?: Omit<UseQueryOptions<TData, TError, TData, QueryKey>, "queryKey" | "queryFn">,
) {
  return useQuery<TData, TError, TData, QueryKey>({
    queryKey,
    queryFn,
    ...options,
  });
}

/**
 * Wrapper around useMutation that auto-invalidates a configurable list of
 * query keys when the mutation succeeds. Pass `invalidates: ["tenants"]` to
 * blow away every tenant query, or finer-grained keys for surgical updates.
 */
export interface TypedMutationOptions<TData, TVariables, TError = Error>
  extends Omit<
    UseMutationOptions<TData, TError, TVariables, unknown>,
    "mutationFn"
  > {
  invalidates?: QueryKey[];
}

export function useTypedMutation<TData, TVariables, TError = Error>(
  mutationFn: (vars: TVariables) => Promise<TData>,
  options?: TypedMutationOptions<TData, TVariables, TError>,
) {
  const qc = useQueryClient();
  return useMutation<TData, TError, TVariables, unknown>({
    mutationFn,
    ...options,
    onSuccess: async (data, vars, ctx, mutationCtx: MutationFunctionContext) => {
      if (options?.invalidates) {
        await Promise.all(
          options.invalidates.map((key) =>
            qc.invalidateQueries({ queryKey: key }),
          ),
        );
      }
      await options?.onSuccess?.(data, vars, ctx, mutationCtx);
    },
  });
}
