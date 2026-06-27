"""
Graph-related API Routes
Uses project context mechanism with server-side state persistence
"""

import os
import traceback
import threading
from flask import request, jsonify, current_app

from . import graph_bp
from ..config import Config
from ..services.ontology_generator import OntologyGenerator
from ..services.graph_builder import GraphBuilderService
from ..services.text_processor import TextProcessor
from ..services.ontology_validator import validate_ontology
from ..utils.file_parser import FileParser
from ..utils.logger import get_logger
from ..utils import t, get_locale, set_locale
from ..models.task import TaskManager, TaskStatus
from ..models.project import ProjectManager, ProjectStatus
from ..auth.ownership import current_user_id
from ..auth.accounts import current_account_id, is_superadmin, require_account_access
from ..auth.graph_access import require_graph_account_access
from ..auth.decorators import superadmin_required

# Get logger
logger = get_logger('mirofish.api')


def _get_storage():
    """Get Neo4jStorage from Flask app extensions."""
    storage = current_app.extensions.get('neo4j_storage')
    if not storage:
        raise ValueError("GraphStorage not initialized — check Neo4j connection")
    return storage


def allowed_file(filename: str) -> bool:
    """Check if file extension is allowed"""
    if not filename or '.' not in filename:
        return False
    ext = os.path.splitext(filename)[1].lower().lstrip('.')
    return ext in Config.ALLOWED_EXTENSIONS


# ============== Project Management Interface ==============

@graph_bp.route('/project/<project_id>', methods=['GET'])
def get_project(project_id: str):
    """
    Get project details
    """
    project = ProjectManager.get_project(project_id)

    if not project:
        return jsonify({
            "success": False,
            "error": t('api.projectNotFound', id=project_id)
        }), 404

    try:
        require_account_access(project.account_id)
    except PermissionError:
        return jsonify({
            "success": False,
            "error": t('api.projectNotFound', id=project_id)
        }), 404

    return jsonify({
        "success": True,
        "data": project.to_dict()
    })


@graph_bp.route('/project/list', methods=['GET'])
def list_projects():
    """
    List all projects
    """
    limit = request.args.get('limit', 50, type=int)
    projects = ProjectManager.list_projects(
        limit=limit,
        account_id=current_account_id(),
        include_all=is_superadmin()
    )

    return jsonify({
        "success": True,
        "data": [p.to_dict() for p in projects],
        "count": len(projects)
    })


@graph_bp.route('/project/<project_id>', methods=['DELETE'])
def delete_project(project_id: str):
    """
    Delete project
    """
    project = ProjectManager.get_project(project_id)

    if not project:
        return jsonify({
            "success": False,
            "error": t('api.projectNotFound', id=project_id)
        }), 404

    try:
        require_account_access(project.account_id)
    except PermissionError:
        return jsonify({
            "success": False,
            "error": t('api.projectNotFound', id=project_id)
        }), 404

    success = ProjectManager.delete_project(project_id)

    if not success:
        return jsonify({
            "success": False,
            "error": t('api.projectDeleteFailed', id=project_id)
        }), 404

    return jsonify({
        "success": True,
        "message": t('api.projectDeleted', id=project_id)
    })


@graph_bp.route('/project/<project_id>/reset', methods=['POST'])
def reset_project(project_id: str):
    """
    Reset project status (for rebuilding graph)
    """
    project = ProjectManager.get_project(project_id)

    if not project:
        return jsonify({
            "success": False,
            "error": t('api.projectNotFound', id=project_id)
        }), 404

    try:
        require_account_access(project.account_id)
    except PermissionError:
        return jsonify({
            "success": False,
            "error": t('api.projectNotFound', id=project_id)
        }), 404

    # Reset to ontology generated state
    if project.ontology:
        project.status = ProjectStatus.ONTOLOGY_GENERATED
    else:
        project.status = ProjectStatus.CREATED

    project.graph_id = None
    project.graph_build_task_id = None
    project.error = None
    ProjectManager.save_project(project)

    return jsonify({
        "success": True,
        "message": t('api.projectReset', id=project_id),
        "data": project.to_dict()
    })


# ============== Step 01 Pause Gate: Persist Human-Edited Ontology ==============

@graph_bp.route('/project/<project_id>/ontology', methods=['PUT'])
def save_ontology(project_id: str):
    """Persist a human-edited ontology after validation (Step 01 pause gate)."""
    try:
        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({"success": False, "error": t('api.projectNotFound', id=project_id)}), 404
        try:
            require_account_access(project.account_id)
        except PermissionError:
            return jsonify({"success": False, "error": t('api.projectNotFound', id=project_id)}), 404

        if project.status == ProjectStatus.GRAPH_BUILDING:
            return jsonify({"success": False, "error": t('api.graphBuilding')}), 409

        data = request.get_json(silent=True) or {}
        ontology = data.get("ontology") or {}
        ontology = {
            "entity_types": ontology.get("entity_types", []),
            "edge_types": ontology.get("edge_types", []),
        }
        result = validate_ontology(ontology)
        if result["errors"]:
            return jsonify({
                "success": False,
                "error": t('api.ontologyValidationFailed'),
                "violations": result["errors"],
            }), 400

        project.ontology = ontology
        if "analysis_summary" in data:
            project.analysis_summary = data.get("analysis_summary") or ""
        project.status = ProjectStatus.ONTOLOGY_GENERATED
        ProjectManager.save_project(project)
        return jsonify({
            "success": True,
            "data": {
                "ontology": project.ontology,
                "analysis_summary": project.analysis_summary,
                "warnings": result["warnings"],
            },
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


# ============== Interface 1: Upload Files and Generate Ontology ==============

@graph_bp.route('/ontology/generate', methods=['POST'])
def generate_ontology():
    """
    Interface 1: Upload files and analyze to generate ontology definition

    Request method: multipart/form-data

    Parameters:
        files: Uploaded files (PDF/MD/TXT), multiple allowed
        simulation_requirement: Simulation requirement description (required)
        project_name: Project name (optional)
        additional_context: Additional notes (optional)

    Response:
        {
            "success": true,
            "data": {
                "project_id": "proj_xxxx",
                "ontology": {
                    "entity_types": [...],
                    "edge_types": [...],
                    "analysis_summary": "..."
                },
                "files": [...],
                "total_text_length": 12345
            }
        }
    """
    try:
        logger.info("=== Starting ontology generation ===")

        # Get parameters
        simulation_requirement = request.form.get('simulation_requirement', '')
        project_name = request.form.get('project_name', 'Unnamed Project')
        additional_context = request.form.get('additional_context', '')

        logger.debug(f"Project name: {project_name}")
        logger.debug(f"Simulation requirement: {simulation_requirement[:100]}...")

        if not simulation_requirement:
            return jsonify({
                "success": False,
                "error": t('api.requireSimulationRequirement')
            }), 400

        # Get uploaded files
        uploaded_files = request.files.getlist('files')
        if not uploaded_files or all(not f.filename for f in uploaded_files):
            return jsonify({
                "success": False,
                "error": t('api.requireFileUpload')
            }), 400

        # Create project
        project = ProjectManager.create_project(
            name=project_name,
            owner_id=current_user_id(),
            account_id=current_account_id()
        )
        project.simulation_requirement = simulation_requirement
        logger.info(f"Project created: {project.project_id}")
        
        # Save files and extract text
        document_texts = []
        all_text = ""

        for file in uploaded_files:
            if file and file.filename and allowed_file(file.filename):
                # Save file to project directory
                file_info = ProjectManager.save_file_to_project(
                    project.project_id,
                    file,
                    file.filename
                )
                project.files.append({
                    "filename": file_info["original_filename"],
                    "size": file_info["size"]
                })

                # Extract text
                text = FileParser.extract_text(file_info["path"])
                text = TextProcessor.preprocess_text(text)
                document_texts.append(text)
                all_text += f"\n\n=== {file_info['original_filename']} ===\n{text}"

        if not document_texts:
            ProjectManager.delete_project(project.project_id)
            return jsonify({
                "success": False,
                "error": t('api.noDocProcessed')
            }), 400

        # Save extracted text
        project.total_text_length = len(all_text)
        ProjectManager.save_extracted_text(project.project_id, all_text)
        logger.info(f"Text extraction completed, total {len(all_text)} characters")

        # Generate ontology
        logger.info("Calling LLM to generate ontology definition...")
        generator = OntologyGenerator()
        ontology = generator.generate(
            document_texts=document_texts,
            simulation_requirement=simulation_requirement,
            additional_context=additional_context if additional_context else None
        )

        # Save ontology to project
        entity_count = len(ontology.get("entity_types", []))
        edge_count = len(ontology.get("edge_types", []))
        logger.info(f"Ontology generation completed: {entity_count} entity types, {edge_count} relation types")
        
        project.ontology = {
            "entity_types": ontology.get("entity_types", []),
            "edge_types": ontology.get("edge_types", [])
        }
        project.analysis_summary = ontology.get("analysis_summary", "")
        project.status = ProjectStatus.ONTOLOGY_GENERATED
        ProjectManager.save_project(project)
        logger.info(f"=== Ontology generation completed === Project ID: {project.project_id}")
        
        return jsonify({
            "success": True,
            "data": {
                "project_id": project.project_id,
                "project_name": project.name,
                "ontology": project.ontology,
                "analysis_summary": project.analysis_summary,
                "files": project.files,
                "total_text_length": project.total_text_length
            }
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Interface 2: Build Graph ==============

@graph_bp.route('/build', methods=['POST'])
def build_graph():
    """
    Interface 2: Build graph based on project_id

    Request (JSON):
        {
            "project_id": "proj_xxxx",  // Required: from interface 1
            "graph_name": "Graph name",    // Optional
            "chunk_size": 500,          // Optional, default 500
            "chunk_overlap": 50         // Optional, default 50
        }

    Response:
        {
            "success": true,
            "data": {
                "project_id": "proj_xxxx",
                "task_id": "task_xxxx",
                "message": "Graph build task started"
            }
        }
    """
    try:
        logger.info("=== Starting graph build ===")

        # Parse request
        data = request.get_json() or {}
        project_id = data.get('project_id')
        logger.debug(f"Request parameters: project_id={project_id}")
        
        if not project_id:
            return jsonify({
                "success": False,
                "error": t('api.requireProjectId')
            }), 400

        # Get project
        project = ProjectManager.get_project(project_id)
        if not project:
            return jsonify({
                "success": False,
                "error": t('api.projectNotFound', id=project_id)
            }), 404

        try:
            require_account_access(project.account_id)
        except PermissionError:
            return jsonify({
                "success": False,
                "error": t('api.projectNotFound', id=project_id)
            }), 404

        # Check project status
        force = data.get('force', False)  # Force rebuild

        if project.status == ProjectStatus.CREATED:
            return jsonify({
                "success": False,
                "error": t('api.ontologyNotGenerated')
            }), 400

        if project.status == ProjectStatus.GRAPH_BUILDING and not force:
            return jsonify({
                "success": False,
                "error": t('api.graphBuilding'),
                "task_id": project.graph_build_task_id
            }), 400

        # If force rebuild, reset status
        if force and project.status in [ProjectStatus.GRAPH_BUILDING, ProjectStatus.FAILED, ProjectStatus.GRAPH_COMPLETED]:
            project.status = ProjectStatus.ONTOLOGY_GENERATED
            project.graph_id = None
            project.graph_build_task_id = None
            project.error = None

        # Get configuration
        graph_name = data.get('graph_name', project.name or 'MiroFish Graph')
        chunk_size = data.get('chunk_size', project.chunk_size or Config.DEFAULT_CHUNK_SIZE)
        chunk_overlap = data.get('chunk_overlap', project.chunk_overlap or Config.DEFAULT_CHUNK_OVERLAP)

        # Update project configuration
        project.chunk_size = chunk_size
        project.chunk_overlap = chunk_overlap

        # Get extracted text
        text = ProjectManager.get_extracted_text(project_id)
        if not text:
            return jsonify({
                "success": False,
                "error": t('api.textNotFound')
            }), 400

        # Get ontology
        ontology = project.ontology
        if not ontology:
            return jsonify({
                "success": False,
                "error": t('api.ontologyNotFound')
            }), 400

        # Get storage in request context (background thread cannot access current_app)
        storage = _get_storage()

        # Capture user id and account id in request context to propagate into the background thread
        owner_id = current_user_id()
        account_id = current_account_id()

        # Capture locale in request context to propagate into the background thread
        locale = get_locale()

        # Create async task
        task_manager = TaskManager()
        task_id = task_manager.create_task(f"Build graph: {graph_name}")
        logger.info(f"Graph build task created: task_id={task_id}, project_id={project_id}")
        
        # Update project status
        project.status = ProjectStatus.GRAPH_BUILDING
        project.graph_build_task_id = task_id
        ProjectManager.save_project(project)

        # Start background task
        def build_task():
            set_locale(locale)
            build_logger = get_logger('mirofish.build')
            try:
                build_logger.info(f"[{task_id}] Starting graph build...")
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.PROCESSING,
                    message=t('progress.initGraphService')
                )

                # Create graph builder service (storage passed from outer closure)
                builder = GraphBuilderService(storage=storage)

                # Chunk text
                task_manager.update_task(
                    task_id,
                    message=t('progress.textChunking'),
                    progress=5
                )
                chunks = TextProcessor.split_text(
                    text,
                    chunk_size=chunk_size,
                    overlap=chunk_overlap
                )
                total_chunks = len(chunks)

                # Create graph
                task_manager.update_task(
                    task_id,
                    message=t('progress.creatingZepGraph'),
                    progress=10
                )
                graph_id = builder.create_graph(name=graph_name, owner_id=owner_id, account_id=account_id)

                # Update project graph_id
                project.graph_id = graph_id
                ProjectManager.save_project(project)

                # Set ontology
                task_manager.update_task(
                    task_id,
                    message=t('progress.settingOntology'),
                    progress=15
                )
                builder.set_ontology(graph_id, ontology)
                
                # Add text (progress_callback signature is (msg, progress_ratio))
                def add_progress_callback(msg, progress_ratio):
                    progress = 15 + int(progress_ratio * 40)  # 15% - 55%
                    task_manager.update_task(
                        task_id,
                        message=msg,
                        progress=progress
                    )

                task_manager.update_task(
                    task_id,
                    message=t('progress.addingChunks', count=total_chunks),
                    progress=15
                )

                episode_uuids = builder.add_text_batches(
                    graph_id,
                    chunks,
                    batch_size=3,
                    progress_callback=add_progress_callback
                )

                # Neo4j processing is synchronous, no need to wait
                task_manager.update_task(
                    task_id,
                    message="Text processing completed, generating graph data...",
                    progress=90
                )

                # Get graph data
                task_manager.update_task(
                    task_id,
                    message=t('progress.fetchingGraphData'),
                    progress=95
                )
                graph_data = builder.get_graph_data(graph_id)

                # Update project status
                project.status = ProjectStatus.GRAPH_COMPLETED
                ProjectManager.save_project(project)

                node_count = graph_data.get("node_count", 0)
                edge_count = graph_data.get("edge_count", 0)
                build_logger.info(f"[{task_id}] Graph build completed: graph_id={graph_id}, nodes={node_count}, edges={edge_count}")

                # Complete
                task_manager.update_task(
                    task_id,
                    status=TaskStatus.COMPLETED,
                    message=t('progress.graphBuildComplete'),
                    progress=100,
                    result={
                        "project_id": project_id,
                        "graph_id": graph_id,
                        "node_count": node_count,
                        "edge_count": edge_count,
                        "chunk_count": total_chunks
                    }
                )

            except Exception as e:
                # Update project status to failed
                build_logger.error(f"[{task_id}] Graph build failed: {str(e)}")
                build_logger.debug(traceback.format_exc())

                project.status = ProjectStatus.FAILED
                project.error = str(e)
                ProjectManager.save_project(project)

                task_manager.update_task(
                    task_id,
                    status=TaskStatus.FAILED,
                    message=t('progress.buildFailed', error=str(e)),
                    error=traceback.format_exc()
                )

        # Start background thread
        thread = threading.Thread(target=build_task, daemon=True)
        thread.start()

        return jsonify({
            "success": True,
            "data": {
                "project_id": project_id,
                "task_id": task_id,
                "message": t('api.graphBuildStarted', taskId=task_id)
            }
        })
        
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Task Query Interface ==============

@graph_bp.route('/task/<task_id>', methods=['GET'])
def get_task(task_id: str):
    """
    Query task status
    """
    task = TaskManager().get_task(task_id)

    if not task:
        return jsonify({
            "success": False,
            "error": t('api.taskNotFound', id=task_id)
        }), 404

    return jsonify({
        "success": True,
        "data": task.to_dict()
    })


@graph_bp.route('/tasks', methods=['GET'])
@superadmin_required
def list_tasks():
    """
    List all tasks (superadmin only).

    Tasks have no account association, so this blanket enumeration would leak
    cross-account simulation_id/graph_id/report_id metadata. It is a debug/admin
    listing not used by normal (non-superadmin) frontend flows, so it is gated
    to superadmin. /task/<id> remains open (requires an unguessable task_id).
    """
    tasks = TaskManager().list_tasks()
    
    return jsonify({
        "success": True,
        "data": [t.to_dict() for t in tasks],
        "count": len(tasks)
    })


# ============== Graph Data Interface ==============

@graph_bp.route('/data/<graph_id>', methods=['GET'])
def get_graph_data(graph_id: str):
    """
    Get graph data (nodes and edges)
    """
    try:
        try:
            require_graph_account_access(graph_id)
        except PermissionError:
            return jsonify({"success": False, "error": t('api.graphNotFound', id=graph_id)}), 404

        storage = _get_storage()
        builder = GraphBuilderService(storage=storage)
        graph_data = builder.get_graph_data(graph_id)

        return jsonify({
            "success": True,
            "data": graph_data
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500


# ============== Graph Curation Endpoints (node/edge edit/delete, merge) ==============

def _reject_if_building(graph_id):
    """Return a 409 response if the graph's project is currently building, else None."""
    getter = getattr(ProjectManager, "get_project_by_graph_id", None)
    if getter is None:
        return None
    project = getter(graph_id)
    if project and project.status == ProjectStatus.GRAPH_BUILDING:
        return jsonify({"success": False, "error": t('api.graphBuilding')}), 409
    return None


@graph_bp.route('/<graph_id>/node/<uuid>', methods=['PATCH'])
def patch_node(graph_id, uuid):
    try:
        try:
            require_graph_account_access(graph_id)
        except PermissionError:
            return jsonify({"success": False, "error": t('api.graphNotFound', id=graph_id)}), 404
        busy = _reject_if_building(graph_id)
        if busy:
            return busy
        fields = request.get_json(silent=True) or {}
        node = _get_storage().update_node(uuid, fields)
        return jsonify({"success": True, "data": node})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@graph_bp.route('/<graph_id>/node/<uuid>', methods=['DELETE'])
def remove_node(graph_id, uuid):
    try:
        try:
            require_graph_account_access(graph_id)
        except PermissionError:
            return jsonify({"success": False, "error": t('api.graphNotFound', id=graph_id)}), 404
        busy = _reject_if_building(graph_id)
        if busy:
            return busy
        _get_storage().delete_node(uuid)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@graph_bp.route('/<graph_id>/edge/<edge_uuid>', methods=['PATCH'])
def patch_edge(graph_id, edge_uuid):
    try:
        try:
            require_graph_account_access(graph_id)
        except PermissionError:
            return jsonify({"success": False, "error": t('api.graphNotFound', id=graph_id)}), 404
        busy = _reject_if_building(graph_id)
        if busy:
            return busy
        fields = request.get_json(silent=True) or {}
        edge = _get_storage().update_edge(edge_uuid, fields)
        return jsonify({"success": True, "data": edge})
    except ValueError as e:
        return jsonify({"success": False, "error": str(e)}), 404
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@graph_bp.route('/<graph_id>/edge/<edge_uuid>', methods=['DELETE'])
def remove_edge(graph_id, edge_uuid):
    try:
        try:
            require_graph_account_access(graph_id)
        except PermissionError:
            return jsonify({"success": False, "error": t('api.graphNotFound', id=graph_id)}), 404
        busy = _reject_if_building(graph_id)
        if busy:
            return busy
        _get_storage().delete_edge(edge_uuid)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@graph_bp.route('/<graph_id>/merge', methods=['POST'])
def merge_graph_nodes(graph_id):
    try:
        try:
            require_graph_account_access(graph_id)
        except PermissionError:
            return jsonify({"success": False, "error": t('api.graphNotFound', id=graph_id)}), 404
        busy = _reject_if_building(graph_id)
        if busy:
            return busy
        data = request.get_json(silent=True) or {}
        primary = data.get("primary")
        duplicates = data.get("duplicates")
        if not isinstance(primary, str) or not primary or not isinstance(duplicates, list) or not duplicates:
            return jsonify({"success": False, "error": t('api.mergeRequiresNodes')}), 400
        node = _get_storage().merge_nodes(primary, duplicates)
        return jsonify({"success": True, "data": node})
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "traceback": traceback.format_exc()}), 500


@graph_bp.route('/delete/<graph_id>', methods=['DELETE'])
def delete_graph(graph_id: str):
    """
    Delete graph
    """
    try:
        try:
            require_graph_account_access(graph_id)
        except PermissionError:
            return jsonify({"success": False, "error": t('api.graphNotFound', id=graph_id)}), 404

        storage = _get_storage()
        builder = GraphBuilderService(storage=storage)
        builder.delete_graph(graph_id)

        return jsonify({
            "success": True,
            "message": t('api.graphDeleted', id=graph_id)
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e),
            "traceback": traceback.format_exc()
        }), 500
