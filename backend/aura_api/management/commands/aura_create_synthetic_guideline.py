from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from aura_api.config import DATA_DIR


class Command(BaseCommand):
    help = "Create the one-page, clearly synthetic operating-guideline PDF fixture without overwriting a file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--output",
            default=str(DATA_DIR / "examples" / "synthetic_robot_operating_guideline.pdf"),
        )

    def handle(self, *args, **options):
        target = Path(options["output"]).resolve()
        if target.exists():
            raise CommandError(f"Refusing to overwrite existing file: {target}")
        target.parent.mkdir(parents=True, exist_ok=True)
        writer = PdfWriter()
        page = writer.add_blank_page(width=612, height=792)
        font = DictionaryObject({
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        })
        page[NameObject("/Resources")] = DictionaryObject({
            NameObject("/Font"): DictionaryObject({NameObject("/F1"): font}),
        })
        lines = [
            "SYNTHETIC ROBOT OPERATING GUIDELINE",
            "Fictional retrieval-demo content; not an approved safety procedure.",
            "Before a pick operation, confirm the task is authorized.",
            "Verify the workspace is clear and the target is identified",
            "in the approved task plan.",
            "Confirm the gripper state is appropriate for the task.",
            "Keep the emergency stop accessible and protective guards",
            "or interlocks active.",
            "If any prerequisite is uncertain, stop and request qualified review.",
            "This sample defines no motion, speed, force, or deployment commands.",
        ]
        stream = DecodedStreamObject()
        commands = ["BT /F1 12 Tf 72 750 Td"]
        for index, line in enumerate(lines):
            safe_line = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
            if index:
                commands.append("0 -28 Td")
            commands.append(f"({safe_line}) Tj")
        commands.append("ET")
        stream.set_data(" ".join(commands).encode("latin-1"))
        page[NameObject("/Contents")] = writer._add_object(stream)
        writer.add_metadata({
            "/Title": "Synthetic Robot Operating Guideline",
            "/Author": "AURA synthetic demo fixture",
        })
        with target.open("xb") as output:
            writer.write(output)
        self.stdout.write(self.style.SUCCESS(f"Created synthetic PDF fixture: {target}"))
