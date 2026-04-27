#!/usr/bin/env python3
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))


def main():
    parser = argparse.ArgumentParser(description='Prospector B2B Pipeline')
    parser.add_argument('--phase',      required=True, choices=['A', 'B', 'C', 'D'])
    parser.add_argument('--ccaa',       default='catalunya',  help='CCAA objetivo (Fase A)')
    parser.add_argument('--sector',     default=None,         help='Sector específico (Fase A, opcional)')
    parser.add_argument('--lead-id',    type=int, default=None, help='Procesar un lead concreto (Fases B/C)')
    parser.add_argument('--queries',    type=int, default=8,  help='Queries a generar (Fase A, default 8)')
    parser.add_argument('--results',    type=int, default=10, help='Resultados por query (Fase A, default 10)')
    parser.add_argument('--max-leads',  type=int, default=None, help='Techo de leads válidos (Fase A)')
    parser.add_argument('--lang',       default='es',         help='Idioma subtítulos YouTube (Fase B, default es)')
    parser.add_argument('--max-videos', type=int, default=20, help='Máx vídeos por canal YouTube (Fase B)')
    args = parser.parse_args()

    if args.phase == 'A':
        from pipeline.phase_a.discover import run as run_a
        run_a(
            ccaa=args.ccaa,
            sector=args.sector,
            n_queries=args.queries,
            results_per_query=args.results,
            max_leads=args.max_leads,
        )

    elif args.phase == 'B':
        from pipeline.phase_b.web_audit import run as run_web
        from pipeline.phase_b.linkedin import run as run_linkedin
        from pipeline.phase_b.youtube import run as run_youtube
        run_web(lead_id=args.lead_id)
        run_linkedin(lead_id=args.lead_id)
        run_youtube(lead_id=args.lead_id, lang=args.lang, max_videos=args.max_videos)

    elif args.phase == 'C':
        from pipeline.phase_c.report import run as run_c
        run_c(lead_id=args.lead_id)

    elif args.phase == 'D':
        from pipeline.phase_d.outreach import run as run_d
        run_d()


if __name__ == '__main__':
    main()
