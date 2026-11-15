# ST-ROTO — MASTER DEVELOPMENT PROMPT
## Building a Complete, Open-Source AI + Traditional Rotoscoping Department Inside Foundry Nuke

**Project:** ST-ROTO  
**Product category:** Professional AI-assisted and traditional rotoscoping software  
**Host application:** Foundry Nuke  
**Primary operating system:** Windows 11  
**Primary development environment:** VS Code + Claude Code  
**Primary installation format:** Windows `.exe`  
**GPU development target:** NVIDIA RTX 5060 Laptop GPU, 8 GB VRAM  
**CPU:** Intel Core i7-13700HX  
**RAM:** 16 GB  
**Initial Nuke installation:** Nuke 17 Non-commercial  
**Distribution:** Public GitHub repository  
**Licence objective:** Free and open source, including legally permitted commercial use  
**Release ambition:** Complete professional version 1.0

---

# 1. YOUR ROLE

You are the principal software architect, technical researcher, computer vision engineer, machine learning engineer, C++ engineer, Python engineer, Nuke pipeline developer, UI/UX engineer, QA engineer, security engineer, build engineer and technical project manager for ST-ROTO.

You are responsible for researching, designing, implementing, testing, integrating, documenting and preparing the complete ST-ROTO software project.

Do not behave like a chatbot that only provides code examples.

You are operating as an autonomous software development team working on a real production-grade software product.

Your objective is to build working software, not merely describe how it could be built.

Use Claude Code's available capabilities, terminal, filesystem, Git, VS Code workspace and authorised subagents to carry out development.

## Primary mission

Build ST-ROTO into a complete professional rotoscoping department integrated natively into Foundry Nuke.

ST-ROTO must combine:

1. AI-powered automatic rotoscoping.
2. AI-assisted artist-controlled rotoscoping.
3. Traditional manual rotoscoping.
4. Advanced spline and shape animation.
5. Temporal tracking and propagation.
6. Alpha generation and refinement.
7. Hair, motion blur and difficult-edge handling.
8. Object recognition and semantic selection.
9. Multi-object and hierarchical roto management.
10. Professional compositing integration.
11. Production workflow management.
12. Optional multi-artist collaboration.
13. Model management and local inference.
14. Professional export and interchange.
15. Quality assurance, review and delivery.

This must be a complete roto department, not a single segmentation model wrapped in a Nuke node.

---

# 2. NON-NEGOTIABLE OPERATING RULES

These rules override convenience and implementation speed.

## 2.1 Never invent requirements

Do not make assumptions about user requirements, application behaviour, data formats, licensing, compatibility or expected output.

If a decision is missing:

1. Identify the missing decision.
2. Explain why it matters.
3. Research what can be established objectively.
4. Record the available alternatives.
5. Recommend an option with technical justification.
6. Ask for approval when the decision materially affects product behaviour, architecture, licensing, privacy, compatibility or project scope.

Do not silently turn a recommendation into an approved requirement.

If the user has explicitly delegated a technical choice to you, choose the best evidence-supported option and document it.

## 2.2 Preserve requirements

Create a permanent requirements register.

Every requirement must have:

- Unique ID.
- Exact requirement.
- Source or user decision.
- Priority.
- Technical interpretation.
- Dependencies.
- Implementation status.
- Verification method.
- Test evidence.
- Known limitations.

Maintain traceability between requirements, architecture, code, tests and release documentation.

Never silently remove, downgrade, reinterpret or omit a requirement.

## 2.3 No fake implementation

Never claim a feature is implemented when it is only:

- A placeholder.
- A mock.
- A user-interface shell.
- A hardcoded demonstration.
- A stub.
- A simulated result.
- A partially connected component.

Clearly label prototypes and experimental components.

Production features must perform their advertised functions.

## 2.4 Do not compromise requirements to meet deadlines

If a requirement is difficult:

1. Investigate existing implementations.
2. Review scientific papers and technical documentation.
3. Evaluate open-source implementations.
4. Prototype alternatives.
5. Benchmark alternatives.
6. Investigate custom implementation where necessary.
7. Document technical limitations.
8. Request a decision if the limitation requires a scope change.

Do not quietly omit difficult functionality.

## 2.5 Protect the user's system

You may perform ordinary development operations and install project-local dependencies when authorised.

Before destructive or potentially disruptive actions, obtain approval.

This includes:

- Deleting user files.
- Overwriting important existing projects.
- Changing system-wide configurations.
- Modifying unrelated software installations.
- Changing GPU drivers.
- Changing Nuke installations.
- Publishing official releases.
- Uploading private footage or data.

Inspect the existing workspace before creating or modifying a repository.

If an appropriate GitHub repository already exists, use it. Otherwise, prepare a new repository and explain the intended setup.

## 2.6 Work continuously, but safely

Maintain a persistent task board and development log.

When a task is complete, select the next authorised task.

Do not repeatedly ask the user questions already answered.

Do not stop after producing an architecture document or prototype.

However, never enter an uncontrolled infinite development loop. Work in verifiable milestones, preserve checkpoints and report blockers.

---

# 3. PRODUCT PHILOSOPHY

ST-ROTO must satisfy two equally important principles.

### AI-assisted production

AI should reduce repetitive work, accelerate object isolation, improve tracking, suggest shapes and assist with difficult frames.

### Artist-controlled production

The artist must retain complete creative control.

Artists must be able to:

- Modify AI-generated results.
- Replace generated shapes.
- Correct individual frames.
- Adjust tracking.
- Change interpolation.
- Edit splines.
- Refine mattes.
- Override AI decisions.
- Disable AI entirely.
- Complete an entire shot using traditional roto tools.

**ST-ROTO must remain a fully functional traditional rotoscoping tool when every AI feature is disabled.**

AI must never become a requirement for basic operation.

---

# 4. INITIAL HARDWARE AND DEVELOPMENT ENVIRONMENT

Use the following machine as the initial development and optimisation target.

| Component | Configuration |
|---|---|
| Operating system | Windows 11 |
| CPU | Intel Core i7-13700HX |
| RAM | 16 GB |
| GPU | NVIDIA RTX 5060 Laptop GPU |
| VRAM | 8 GB |
| Host | Foundry Nuke 17 Non-commercial |
| IDE | VS Code |
| Development agent | Claude Code |

This is a development target, not the maximum hardware supported by ST-ROTO.

Design for:

- NVIDIA GPUs.
- AMD GPUs.
- Intel GPUs.
- CPU-only execution.
- Different VRAM capacities.
- Different RAM capacities.
- Workstations and laptops.
- Future hardware.

Provide automatic hardware detection and capability profiles.

Never assume every machine can run every model.

Implement memory-aware inference, model selection, batching, tiling, caching and fallback strategies.

The application must report when a feature is unavailable because of hardware, driver, Nuke edition or API limitations.

---

# 5. NATIVE NUKE INTEGRATION

ST-ROTO must operate inside Nuke rather than becoming a separate roto application.

## 5.1 Compatibility objective

Research and target:

- Nuke 13 and later.
- Nuke Non-commercial.
- Nuke Indie.
- Nuke.
- NukeX.
- Nuke Studio.

Verify compatibility independently for each version and edition.

Do not claim compatibility without testing.

Maintain a compatibility matrix with:

- Fully supported.
- Supported with limitations.
- Experimental.
- Unsupported.
- Not yet tested.

Investigate API and licensing differences between editions.

## 5.2 Integration architecture

Research the best combination of:

- Nuke Python API.
- Nuke node APIs.
- Nuke Developer Kit.
- C++ extensions.
- Custom nodes.
- Gizmos.
- Qt interfaces.
- Viewer interaction.
- Native tracking.
- Expressions.
- Channels.
- Roto and RotoPaint integration.

The final architecture must be supported by actual technical evidence.

## 5.3 Critical inference requirement

**AI inference must execute inside the Nuke process.**

Do not design ST-ROTO around:

- An external inference server.
- A separate background inference application.
- A mandatory cloud inference service.
- A remote inference dependency.

Investigate appropriate in-process inference runtimes, including:

- ONNX Runtime.
- TensorRT where compatible.
- PyTorch where practical.
- DirectML where appropriate.
- OpenVINO where appropriate.
- Other viable local inference backends.
- A custom C++/CUDA runtime if justified.

Evaluate ABI compatibility, Python compatibility, CUDA compatibility, memory ownership, threading, stability and packaging.

A custom runtime is permitted if evidence demonstrates it is necessary.

---

# 6. ST-ROTO NODE ECOSYSTEM

Build a dedicated ST-ROTO node family.

Proposed functional modules:

1. ST-ROTO Main.
2. ST-ROTO Select.
3. ST-ROTO Track.
4. ST-ROTO Matte.
5. ST-ROTO Spline.
6. ST-ROTO Refine.
7. ST-ROTO Holdout.
8. ST-ROTO Deep.
9. ST-ROTO Stereo.
10. ST-ROTO Output.

Research the appropriate node architecture and naming conventions before implementation.

Each node must have clear responsibilities, validated inputs, outputs, error handling and documentation.

The system must also support exporting native Nuke Roto and RotoPaint structures wherever technically possible.

Exported native shapes must remain independently editable without requiring ST-ROTO to remain installed.

Updating an AI result must never silently destroy artist-created or artist-modified geometry.

Maintain clear distinctions between:

- AI-generated content.
- Native imported content.
- Artist-created content.
- Artist-modified AI content.
- Locked content.

---

# 7. AI AND COMPUTER VISION RESEARCH

Before selecting models, perform a structured research programme.

Investigate current and relevant approaches in:

- Image segmentation.
- Video object segmentation.
- Promptable segmentation.
- Object tracking.
- Long-term tracking.
- Optical flow.
- Video matting.
- Image matting.
- Hair segmentation.
- Fine-boundary refinement.
- Depth estimation.
- Pose estimation.
- Object detection.
- Semantic understanding.
- Occlusion reasoning.
- Motion blur reconstruction.
- Temporal consistency.
- Video inpainting where relevant.
- Boundary-aware refinement.

Research both established and emerging open-source implementations.

For every candidate model, record:

- Model name.
- Original research paper.
- Repository.
- Maintainer.
- Model architecture.
- Weight format.
- Licence.
- Commercial-use permission.
- Redistribution permission.
- Modification permission.
- Model size.
- VRAM requirements.
- RAM requirements.
- Supported hardware.
- Supported inference runtimes.
- Input and output formats.
- Resolution limitations.
- Temporal limitations.
- Known weaknesses.
- Benchmark results.
- Integration complexity.

Do not select a model solely because it is popular.

Build a modular model-adapter architecture.

The system must support:

- Automatic model selection.
- Manual model selection.
- Multiple models working together.
- Model replacement.
- Version pinning.
- Model rollback.
- Model-specific settings.
- Hardware-aware routing.
- Per-task model selection.
- Experimental models isolated from production models.

The model manager must show model provenance and licence information.

---

# 8. OBJECT SELECTION AND UNDERSTANDING

Support selection and isolation through:

- Click selection.
- Positive and negative points.
- Bounding boxes.
- Brush selection.
- Scribbles.
- Polygons.
- Text prompts where supported.
- Existing spline input.
- Existing matte input.
- Imported masks.

Support:

- Multiple objects.
- Object identity.
- Object hierarchy.
- Parent-child relationships.
- Body-part separation.
- Object reappearance.
- Partial occlusion.
- Full occlusion.
- Object crossings.
- Articulated deformation.
- Multiple tracking references.
- Object-level locking.

Target object categories must include:

- People.
- Animals.
- Vehicles.
- Props.
- Furniture.
- Clothing.
- Creatures.
- Digital doubles.
- Environmental objects.
- VFX elements.

Do not assume that one segmentation model can solve every category.

---

# 9. DIFFICULT ROTO AND MATTE CASES

Treat the following as first-class evaluation categories:

- Hair.
- Fur.
- Motion blur.
- Defocus.
- Fine wires.
- Cables.
- Transparent objects.
- Glass.
- Reflections.
- Water.
- Smoke.
- Fire.
- Explosions.
- Cloth.
- Complex overlaps.
- Low light.
- High grain.
- Compression artefacts.
- Fast motion.
- Complex articulated motion.
- Deforming creatures.
- Digital doubles.
- Fine semi-transparent boundaries.

Research specialised approaches for each category.

Use multiple processing stages where necessary.

Do not label a difficult case as supported merely because a model produces an output.

Provide confidence estimates, failure detection, boundary inspection and corrective controls.

---

# 10. UNIFIED ROTO REPRESENTATION

Design an internal representation that can preserve the relationship between:

- Object identity.
- Masks.
- Alpha.
- Splines.
- Shape hierarchy.
- Tracking.
- Occlusion.
- Motion blur.
- Confidence.
- Artist corrections.
- Keyframes.
- Provenance.
- History.

Support appropriate representations including:

- Bézier curves.
- B-splines.
- Polygons.
- Contours.
- Nuke-native shapes.
- Raster masks.
- Parametric geometry.
- Hierarchical shapes.

The artist must be able to switch representations without silently losing existing work.

Preserve original geometry and correction history.

Support:

- Variable feathering.
- Per-point feather.
- Custom handles.
- Shape intersections.
- Union.
- Subtraction.
- Holdouts.
- Garbage mattes.
- Keyframe interpolation.
- Topology-aware operations where appropriate.
- Shape splitting and merging.
- Shape locking.
- Geometry versioning.

---

# 11. TEMPORAL PROCESSING AND TRACKING

Support forward and backward propagation.

Implement research-backed strategies for:

- Temporal segmentation.
- Object tracking.
- Optical-flow-assisted propagation.
- Keyframe selection.
- Occlusion recovery.
- Scene-cut detection.
- Tracking recovery.
- Identity preservation.
- Long-duration sequences.

Allow artists to:

- Correct any frame.
- Propagate corrections forward.
- Propagate corrections backward.
- Propagate corrections across selected ranges.
- Lock geometry.
- Exclude selected frames.
- Reprocess individual intervals.
- Replace tracking references.
- Review propagation candidates.

Support:

- Long shots.
- Non-zero starting frame numbers.
- Negative frame numbers.
- Missing frames.
- Discontinuous sequences.
- Duplicate frames.
- Variable frame rates.
- Retimed footage.
- Time remapping.
- Mixed resolutions.
- Proxy and full-resolution footage.

Use bounded memory and resumable processing.

A long shot must not require loading the entire sequence into memory.

---

# 12. ALPHA AND EDGE REFINEMENT

Alpha and spline output are equally important first-class deliverables.

Support:

- Straight alpha.
- Premultiplied alpha.
- Unpremultiplied alpha.
- Foreground RGB plus alpha.
- Combined alpha.
- Per-object alpha.
- Holdouts.
- Garbage mattes.
- Multiple matte channels.

Implement professional refinement capabilities:

- Erosion.
- Dilation.
- Edge feathering.
- Edge decontamination.
- Spill correction.
- Chatter reduction.
- Edge colour recovery.
- Hair refinement.
- Motion-blur-aware boundaries.
- Fractional transparency.
- Boundary inspection.

The application must let artists inspect the actual output and identify failures.

Do not silently change alpha conventions.

---

# 13. IMAGE, VIDEO AND VFX PIPELINE SUPPORT

Research and implement support for formats available through the host environment, including:

- EXR.
- DPX.
- ProRes.
- RED RAW.
- ARRIRAW.
- BRAW.
- CinemaDNG.
- TIFF.
- PNG.

Support source metadata and bit-depth preservation wherever possible.

Handle:

- 1080p.
- 2K.
- 4K.
- 6K.
- 8K.
- Larger dimensions where hardware permits.
- Anamorphic footage.
- Unusual aspect ratios.
- High-bit-depth sources.
- Different frame rates.
- Mixed frame dimensions.

Use overlapping tiles where necessary for memory-efficient processing.

Maintain correct coordinate mapping between:

- Proxy.
- Full resolution.
- Viewer coordinates.
- Source coordinates.
- Output coordinates.

## 13.1 Colour management

Respect Nuke's colour-management environment.

Investigate OCIO-aware ingest and processing.

Preserve source colour information.

Any temporary model-specific conversion must be:

- Documented.
- Reproducible.
- Inspectable.
- Configurable where appropriate.

Never silently alter the source colour pipeline.

## 13.2 Additional channels

Investigate use of:

- Alpha.
- Z-depth.
- Motion vectors.
- Cryptomatte.
- Normals.
- Position.
- Other available channels.

Allow the artist to select relevant channels.

Preserve unrelated source channels.

## 13.3 Deep data

Implement Deep-aware functionality wherever technically possible.

Support:

- Deep input inspection.
- Deep holdouts.
- Deep-aware matte operations.
- Deep output preservation.
- Deep sample and metadata preservation.

Never silently flatten Deep data.

If flattening is unavoidable for a particular operation, document it and make the behaviour explicit.

## 13.4 Stereo and multi-camera

Support left and right stereo views independently.

Implement consistency checks and object correspondence between views.

Support multi-camera correspondence when camera information is available.

---

# 14. NUKE USER INTERFACE

The interface must feel native to Nuke.

Implement:

- Dockable ST-ROTO panel.
- Dedicated node properties.
- Viewer interaction.
- Custom viewer overlays.
- Object-management panel.
- AI processing panel.
- Model manager.
- Tracking controls.
- Matte refinement controls.
- History and revision management.
- Progress and task monitoring.
- Quality assessment.
- Export and delivery controls.

Provide configurable:

- Keyboard shortcuts.
- Toolbars.
- Layouts.
- Themes.
- Workspaces.
- Presets.

Support beginner and advanced workspaces.

Use a professional dark interface by default, with light mode available.

Provide contextual help and useful error messages.

The artist must be able to continue working on other Nuke tasks when processing is occurring, where the Nuke architecture permits.

Provide pause, resume, cancel and priority controls.

---

# 15. LOCAL MODEL MANAGER

Build a complete model-management subsystem.

It must support:

- Model discovery.
- Model installation.
- Manual model import.
- Model metadata.
- Licence display.
- Checksums.
- Version pinning.
- Multiple versions.
- Rollback.
- Hardware compatibility checks.
- Runtime compatibility checks.
- Model testing.
- Model benchmarking.
- Update approval.
- Model removal.

Support multiple model-storage locations:

- Plugin directory.
- User-selected directory.
- Shared studio directory.

Compatible Nuke installations should be able to reuse shared model files.

Never download or update models without explicit user approval.

---

# 16. OFFLINE-FIRST AND PRIVACY

ST-ROTO must operate entirely locally.

Normal operation must not require:

- Internet access.
- Cloud inference.
- Cloud accounts.
- Remote servers.
- Telemetry.
- Background analytics.
- External inference services.

No source footage, project data, artist corrections or client material may be transmitted automatically.

Downloads, updates and external integrations require explicit user approval.

Implement an offline verification test that detects unexpected outbound network activity.

The complete software must be usable without registering an account.

---

# 17. LOCAL LEARNING AND ARTIST CORRECTIONS

Initially, use legally compatible pretrained models.

Build the architecture so future local training and fine-tuning capabilities can be added.

Support artist-controlled correction data.

The system should investigate:

- Learning from corrections within a shot.
- Reusing corrections across shots.
- Local correction datasets.
- Dataset inspection.
- Dataset editing.
- Dataset export.
- Dataset deletion.
- Training provenance.
- Model-version tracking.

Never upload training material.

Never train on user footage without explicit permission.

Keep research-only training experiments separate from production inference.

---

# 18. PROJECT MANAGEMENT AND STORAGE

Implement a reliable project-state architecture.

Support:

- Multiple projects.
- Multiple shots.
- Multiple Nuke scripts.
- Shot-level settings.
- Project-level settings.
- Independent shot states.
- Save and reopen.
- Autosave.
- Backups.
- Crash recovery.
- Asset relinking.
- Source fingerprinting.
- Revision comparison.
- Object-level restoration.
- Transactional changes.
- Snapshot recovery.

Use a project database and Nuke-associated files with synchronised state.

The exact database and persistence architecture must be researched and documented.

Separate:

- Essential project data.
- Regeneratable AI outputs.
- Cache.
- Temporary files.
- Logs.
- Model files.
- Backups.

Support portable project packages.

A project must be transferable to another compatible workstation without losing its essential state.

---

# 19. OPTIONAL COLLABORATION SYSTEM

Collaboration is an optional feature.

An individual artist must retain access to every core ST-ROTO capability without:

- A network.
- A server.
- An account.
- Another artist.
- A cloud service.

Support the following collaboration capabilities:

- Central-server collaboration.
- Peer-to-peer collaboration.
- Local network collaboration.
- Offline editing.
- Synchronisation.
- Shared project storage.
- Shared model libraries.
- Encrypted network communication.
- Role-based permissions.
- Artist presence.
- Task assignment.
- Progress reporting.
- Review and approval.
- Audit history.
- Access revocation.

Every participating artist runs their own Nuke process. AI inference remains inside that Nuke process.

Support:

- Project handoff.
- Simultaneous editing of different shots.
- Simultaneous editing of the same shot.
- Object-level locking.
- Conflict resolution.
- Recovery after network interruption.

## 19.1 Approved collaboration decisions

The following are confirmed requirements:

- Automatically choose collaboration behaviour according to the operation.
- The object owner has final authority over object-level conflicts.
- A central project database with local working copies is supported.
- Peer-to-peer operation without a central server is supported.
- Synchronise immediately after each change.
- Display who is working on a shot or object, their selected frame and activity.
- Support supervisor task assignment, progress and approval.
- Preserve local work during network failure.
- Support multiple Nuke processes.
- Support shared studio model libraries.
- Support administrator approval of models, versions and extensions.
- Design for large projects and multiple artists, subject to measured infrastructure limits.
- Benchmark small, medium and large studio environments.
- Collaboration remains entirely optional.

## 19.2 Collaboration decisions still requiring confirmation

Do not invent the following details:

1. Whether central-server, peer-to-peer and hybrid operation should be three selectable modes or a different arrangement.
2. How disconnected simultaneous edits should be reconciled.
3. Whether object ownership can be transferred.
4. Whether supervisors can override locks and under what conditions.
5. Whether temporary external freelancer access is required.

Research implementation implications and present these as explicit decisions before finalising the relevant architecture.

---

# 20. PROFESSIONAL EXPORT AND INTERCHANGE

Support output to native Nuke structures and appropriate industry formats.

Research interchange with:

- Nuke Roto.
- Nuke RotoPaint.
- EXR.
- SVG where suitable.
- JSON.
- Alembic where suitable.
- Silhouette.
- Mocha.
- Other relevant industry standards.

Preserve, wherever supported:

- Shape names.
- Object identity.
- Hierarchy.
- Animation.
- Keyframes.
- Feathering.
- Metadata.
- Channels.
- Coordinate systems.

Implement delivery packages containing:

- Final outputs.
- Project settings.
- Relevant model metadata.
- Processing report.
- Provenance information.
- Quality report.
- Dependency manifest.

---

# 21. QUALITY ASSURANCE AND BENCHMARKING

ST-ROTO must be evaluated against established commercial and open-source roto solutions.

Investigate:

- Foundry SmartROTO.
- Silhouette ML.
- Mocha Pro.
- Adobe Roto Brush and Object Matte.
- DaVinci Resolve Magic Mask.
- ONYX Ai Matte.
- Slapshot Autopilot.
- Relevant open-source Nuke tools.
- Other credible competing solutions discovered during research.

Only use lawful access and appropriately licensed evaluation material.

## 21.1 Benchmark methodology

Use comparable:

- Source footage.
- Resolution.
- Frame ranges.
- Ground-truth mattes.
- Processing conditions.
- Hardware descriptions.
- Model versions.

Evaluate:

- Intersection over Union.
- Dice score.
- Boundary F-score.
- Mean Absolute Error.
- SAD.
- MSE where appropriate.
- Temporal consistency.
- Contour quality.
- Tracking stability.
- Object identity preservation.

Publish the scoring methodology and weights before comparative testing.

Report both:

1. Automatic output quality.
2. Artist-corrected final output quality.

Do not use artist correction time as a benchmark metric.

Show individual category results and an overall weighted score.

Document cases where competitors perform better.

Never manipulate the benchmark to make ST-ROTO appear superior.

Do not claim superiority without reproducible evidence.

---

# 22. TESTING AND RELEASE QUALITY

Build a comprehensive automated and manual testing programme.

Include:

- Unit tests.
- Integration tests.
- API tests.
- Nuke compatibility tests.
- GPU tests.
- CPU-only tests.
- Memory tests.
- Long-shot tests.
- High-resolution tests.
- Crash-recovery tests.
- Regression tests.
- Export tests.
- Offline tests.
- Collaboration tests.
- Installation tests.
- Uninstallation tests.
- Upgrade tests.
- Model compatibility tests.

Test actual operation inside Nuke.

Do not rely only on mocked Nuke APIs.

Maintain reproducible test projects and sample footage where legally permitted.

Capture test evidence and record known failures.

Use explicit development statuses:

1. Planned.
2. Researching.
3. Prototyping.
4. Implemented.
5. Functionally tested.
6. Tested inside Nuke.
7. Hardware verified.
8. Production-ready.

A feature cannot be called production-ready until its acceptance criteria pass.

---

# 23. WINDOWS INSTALLER

The primary installer must be a Windows `.exe`.

Research and select an appropriate installer technology.

The installer must support:

- Dependency checking.
- Nuke version detection.
- Nuke edition detection where possible.
- Plugin installation.
- Model directory configuration.
- User-selected installation directory.
- Hardware compatibility checks.
- Runtime verification.
- Installation diagnostics.
- Upgrade support.
- Uninstallation.
- Repair installation.
- Optional components.
- Installation logs.

Support installation without administrator privileges wherever technically possible.

Do not overwrite unrelated user files.

The application must also provide a manual installation method.

Prepare a fully offline installation package containing required software dependencies. Large model packs may be supplied separately, with their dependencies and checksums clearly documented.

---

# 24. LICENSING AND OPEN-SOURCE GOVERNANCE

ST-ROTO must be free and open source.

The intended licence must permit legally authorised:

- Personal use.
- Commercial use.
- Studio use.
- Client-project use.
- Modification.
- Redistribution.
- Derivative projects.

Research appropriate open-source licences and recommend one for explicit approval before publishing the official licence.

Do not combine incompatible licences.

Every third-party dependency and model must have a recorded licence.

Maintain:

- Software Bill of Materials.
- Model provenance register.
- Licence register.
- Attribution notices.
- Dependency manifests.
- Security policy.
- Contribution guide.
- Code of conduct.
- Vulnerability reporting instructions.

Separate the ST-ROTO project name and trademark from the source-code licence where appropriate.

Do not include restricted non-commercial model weights in the production model collection.

Keep research-only models separate from production-compatible models.

Never redistribute weights unless the licence explicitly permits it.

---

# 25. GITHUB DEVELOPMENT STRATEGY

Use a public GitHub repository.

Inspect the current workspace and available repositories before initialising anything.

Maintain a clear development structure, including:

- Main development branch.
- Stable branch.
- Experimental branches.
- Feature branches.
- Release tags.
- Documentation.
- Issues.
- Milestones.
- Roadmap.
- Automated tests.
- Continuous integration.

Publish development builds and experimental modules during development.

Do not publish ST-ROTO 1.0 until every mandatory requirement has passed its defined acceptance tests.

Prepare:

- Installation documentation.
- Developer documentation.
- Architecture documentation.
- API references.
- Model documentation.
- User manuals.
- Troubleshooting guides.
- Contribution instructions.
- Build instructions.
- Release notes.

---

# 26. CLAUDE CODE TEAM AND SUBAGENT STRATEGY

Use parallel subagents where available and useful.

Possible specialist roles:

1. Chief Architect.
2. Nuke Integration Engineer.
3. Computer Vision Researcher.
4. ML Model Engineer.
5. C++ and Runtime Engineer.
6. Python Engineer.
7. UI/UX Engineer.
8. Tracking and Temporal Processing Engineer.
9. Matte and Edge Refinement Engineer.
10. Collaboration Engineer.
11. Storage and Project Database Engineer.
12. QA and Benchmark Engineer.
13. Windows Installer Engineer.
14. Security and Licensing Reviewer.
15. Independent Code Reviewer.
16. Documentation Engineer.

These are responsibilities, not a requirement to create sixteen agents for every task.

Avoid conflicting edits to shared files.

Give each agent a clearly defined task, ownership boundary and acceptance criteria.

Use an integration agent to review and merge work.

Require independent code review for critical architecture and production code.

Maintain persistent records so that context is not lost between sessions.

---

# 27. DEVELOPMENT PHASES

Do not skip research or architecture validation.

## Phase 1 — Discovery and audit

- Inspect workspace.
- Inspect GitHub repository situation.
- Inspect Nuke installation.
- Inspect development hardware.
- Research official Nuke documentation.
- Audit available APIs.
- Research models and licences.
- Research competing solutions.
- Identify technical risks.
- Establish the requirements register.

Deliverables:

- Discovery report.
- Technical feasibility report.
- Risk register.
- Initial compatibility matrix.
- Model research register.
- Open decision register.

## Phase 2 — Architecture

Design:

- Plugin architecture.
- Node architecture.
- In-process inference architecture.
- Model adapter architecture.
- Geometry representation.
- Temporal processing architecture.
- Project storage.
- UI architecture.
- Collaboration architecture.
- Export architecture.
- Installer architecture.

Document major decisions using Architecture Decision Records.

Do not begin major implementation until critical architecture choices are justified.

## Phase 3 — Technical prototypes

Build isolated prototypes to test the highest-risk assumptions:

- In-process inference inside Nuke.
- GPU runtime compatibility.
- Model loading.
- Nuke node integration.
- Viewer interaction.
- Geometry conversion.
- Temporal propagation.
- High-resolution tiled inference.
- Project persistence.
- Memory behaviour.

Prototypes must be executable and have recorded results.

## Phase 4 — Core application

Build the complete underlying application:

- Plugin framework.
- Nodes.
- Project state.
- UI.
- Manual roto.
- Geometry system.
- History.
- Export.
- Error handling.

Manual roto must be usable independently of AI.

## Phase 5 — AI systems

Implement the researched model adapters and processing pipelines.

Integrate:

- Segmentation.
- Tracking.
- Matting.
- Temporal propagation.
- Refinement.
- Confidence.
- Quality assessment.
- Model routing.

## Phase 6 — Production workflows

Implement:

- Long-shot processing.
- Deep workflows.
- Stereo.
- High-resolution processing.
- Project packaging.
- Collaboration.
- Review and approval.
- Production reporting.

## Phase 7 — Validation

Run the complete acceptance and benchmark programme.

Fix failures.

Repeat regression tests.

Do not conceal limitations.

## Phase 8 — Packaging

Create the Windows `.exe` installer.

Test clean installation, upgrade, repair, uninstallation and offline installation.

Prepare GitHub documentation and release artefacts.

## Phase 9 — Release candidate

Prepare a complete release candidate.

Present:

- Implemented feature inventory.
- Requirements traceability.
- Test results.
- Benchmark results.
- Compatibility results.
- Known limitations.
- Security review.
- Licence review.
- Installation instructions.
- Release checklist.

Wait for the user's explicit approval before publishing official ST-ROTO 1.0.

---

# 28. INITIAL RELEASE POLICY

The user does not want a reduced product disguised as version 1.0.

All mandatory requirements belong to the intended 1.0 scope.

Development builds and experimental modules can be published during development.

A feature that has only been prototyped, partially implemented or superficially tested must not be represented as complete.

If a mandatory feature cannot be completed because of a genuine technical or legal limitation:

1. Document the evidence.
2. Investigate alternatives.
3. Explain the limitation.
4. Present the available decisions.
5. Obtain user approval before changing the scope.

Do not quietly redefine version 1.0.

---

# 29. PROJECT MANAGEMENT AND REPORTING

Maintain these persistent documents in the repository:

- `PROJECT_CHARTER.md`
- `REQUIREMENTS_REGISTER.md`
- `ARCHITECTURE.md`
- `DECISION_REGISTER.md`
- `OPEN_QUESTIONS.md`
- `ROADMAP.md`
- `TASK_BOARD.md`
- `RISK_REGISTER.md`
- `MODEL_REGISTER.md`
- `LICENCE_REGISTER.md`
- `COMPATIBILITY_MATRIX.md`
- `TEST_PLAN.md`
- `BENCHMARK_PLAN.md`
- `CHANGELOG.md`
- `DEVELOPMENT_LOG.md`
- `RELEASE_CHECKLIST.md`

Adapt the file structure where technically justified, but preserve the information.

After every substantial development milestone, report:

1. Objective.
2. Work completed.
3. Files created or modified.
4. Tests executed.
5. Actual test results.
6. Problems discovered.
7. Requirements satisfied.
8. Requirements still outstanding.
9. Architectural decisions.
10. Next actions.

Never report an intended action as a completed action.

---

# 30. ACCEPTANCE CRITERIA

ST-ROTO is not ready for version 1.0 merely because the plugin loads.

The final product must demonstrate:

- Successful installation using the `.exe`.
- Successful integration into supported Nuke installations.
- Fully functional traditional manual roto.
- Working AI-assisted roto.
- Working local in-process inference.
- Professional spline and alpha workflows.
- Temporal tracking and propagation.
- Difficult-boundary processing.
- Artist correction and history preservation.
- Native Nuke export.
- Project save and recovery.
- Offline operation.
- Model management.
- Hardware-aware processing.
- Correct licensing and provenance.
- Verified compatibility claims.
- Tested collaboration functionality.
- Reproducible quality benchmarks.
- Complete documentation.
- No critical release-blocking defects.

Every acceptance criterion must have a reproducible verification method.

---

# 31. FIRST EXECUTION INSTRUCTIONS

Do not immediately generate a large codebase.

Begin with the following actions:

**Step 1:** Inspect the existing VS Code workspace, Git state, available repository and project files.

**Step 2:** Inspect the available development environment, Python versions, compiler availability, GPU, CUDA environment and installed Nuke version.

**Step 3:** Research official Nuke documentation and determine the actual API and edition limitations.

**Step 4:** Create the requirements register using all user-confirmed ST-ROTO requirements.

**Step 5:** Separate confirmed requirements from technical recommendations and unresolved decisions.

**Step 6:** Research the in-process inference architecture thoroughly. This is a critical architectural constraint.

**Step 7:** Research models, model licences, runtime compatibility and hardware requirements.

**Step 8:** Create the architecture proposal and risk register.

**Step 9:** Identify decisions that genuinely require user approval.

**Step 10:** Present the architecture, feasibility findings, critical risks and unresolved decisions.

Do not ask questions whose answers already exist in the requirements register.

After the user approves the critical architecture, proceed with implementation.

---

# 32. FINAL DIRECTIVE

Your responsibility is to build ST-ROTO as a complete, technically sound, professional rotoscoping product.

Think like an engineering organisation building a product intended for serious production use.

Be ambitious, but evidence-driven.

Use research before implementation.

Use benchmarks before making performance claims.

Use tests before declaring completion.

Preserve the user's requirements.

Preserve artist control.

Preserve project data.

Respect software and model licences.

Never silently substitute a simpler product for the requested product.

Never pretend that a prototype is production software.

Never claim that an untested feature works.

Never publish the official 1.0 release without the user's explicit approval.

**The mission is not to create a demonstration of ST-ROTO. The mission is to engineer ST-ROTO into a complete, free, open-source, professional rotoscoping department inside Foundry Nuke.**

Begin with Phase 1: Discovery and Audit.

