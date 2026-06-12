from functools import partial

from mirage.commands.builtin.generic.grep import grep as generic_grep
from mirage.commands.builtin.grep_helper import pattern_arg
from mirage.commands.registry import command
from mirage.commands.spec import SPECS
from mirage.core.chroma.glob import resolve_glob
from mirage.core.chroma.grep import coarse_filter_slugs, target_slugs
from mirage.core.chroma.read import read_bytes, read_stream
from mirage.core.chroma.readdir import readdir
from mirage.core.chroma.stat import stat_light
from mirage.io.types import ByteSource, IOResult
from mirage.types import PathSpec


@command("grep", resource="chroma", spec=SPECS["grep"])
async def grep(
    accessor,
    paths: list[PathSpec],
    *texts: str,
    **flags: object,
) -> tuple[ByteSource | None, IOResult]:
    index = flags.get("index")
    paths = await resolve_glob(accessor, paths, index)
    pattern = pattern_arg(texts, flags)
    files = paths
    show_filename = False
    if paths and pattern is not None:
        # Pushdown: expand the scope to files and let ChromaDB pre-filter
        # which documents can contain the pattern, so only candidate
        # documents are fetched. The generic grep owns flag handling and
        # output formatting on the surviving files. Skipped when only -f
        # supplies patterns (they are read inside the generic).
        targets = await target_slugs(accessor, paths, index)
        matched = set(await
                      coarse_filter_slugs(accessor,
                                          pattern,
                                          targets,
                                          ignore_case=flags.get("i") is True,
                                          invert=flags.get("v") is True,
                                          fixed_string=flags.get("F") is True))
        prefix = paths[0].prefix
        files = [
            PathSpec.from_str_path(p, prefix) for p, slug in targets.items()
            if slug in matched
        ]
        if not files:
            return b"", IOResult(exit_code=1)
        recursive = flags.get("r") is True or flags.get("R") is True
        show_filename = recursive or len(paths) > 1 or len(targets) > 1
    return await generic_grep(
        files,
        texts,
        {
            **flags, "r": False,
            "R": False
        },
        readdir=readdir,
        stat=stat_light,
        read_bytes=read_bytes,
        read_stream=partial(read_stream, index=index),
        accessor=accessor,
        show_filename=show_filename,
        index=index,
    )
