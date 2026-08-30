package main

import "github.com/spf13/cobra"

func newParseCmd() *cobra.Command {
	var dbPath string
	cmd := &cobra.Command{
		Use:   "parse [path]",
		Short: "Parse a repo into the code graph and exit (no server)",
		Args:  cobra.MaximumNArgs(1),
		RunE: func(cmd *cobra.Command, args []string) error {
			repoRoot, err := resolveRepoPath(args)
			if err != nil {
				return err
			}
			s, err := openStoreAndIndex(cmd, repoRoot, dbPath)
			if err != nil {
				return err
			}
			return s.Close()
		},
	}
	cmd.Flags().StringVar(&dbPath, "db", "", "path to the SQLite graph DB (default: <repo>/.kb-core-ui/graph.db)")
	return cmd
}
