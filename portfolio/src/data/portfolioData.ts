import type { Project, ComboStateNode, TechCategory, CodePattern } from '../types/portfolio';

export const HERO_STATS = [
  { label: 'SIMULATED TICK RATE', value: '120 Hz', subtext: 'Fixed-step determinism' },
  { label: 'MAX INPUT BUFFER WINDOW', value: '16.6 ms', subtext: 'Frame-accurate buffering' },
  { label: 'SPATIAL QUERY SWEEPS', value: '<0.4 ms', subtext: '1,000 active hurtboxes' },
  { label: 'ENGINE KERNELS BUILT', value: '3+', subtext: 'Custom C++ / C# Action Rigs' }
];

export const COMBO_STATES: Record<string, ComboStateNode> = {
  idle: {
    id: 'idle',
    name: 'STANCE_NEUTRAL',
    inputTrigger: 'NONE',
    startupFrames: 0,
    activeFrames: 0,
    recoveryFrames: 0,
    cancelWindowStartFrame: 0,
    damage: 0,
    poiseDamage: 0,
    hitType: 'Light Slash',
    description: 'Neutral combat stance ready to buffer incoming player inputs.',
    nextStates: ['light_1', 'parry']
  },
  light_1: {
    id: 'light_1',
    name: 'LIGHT_ATTACK_01 (QUICK CUT)',
    inputTrigger: 'J (Light)',
    startupFrames: 4,
    activeFrames: 3,
    recoveryFrames: 8,
    cancelWindowStartFrame: 5,
    damage: 180,
    poiseDamage: 25,
    hitType: 'Light Slash',
    description: 'Fast horizontal slash with early cancel window for light-to-heavy combo chains.',
    nextStates: ['light_2', 'heavy_finisher', 'dodge_cancel']
  },
  light_2: {
    id: 'light_2',
    name: 'LIGHT_ATTACK_02 (CROSS RIFT)',
    inputTrigger: 'J (Light)',
    startupFrames: 5,
    activeFrames: 4,
    recoveryFrames: 10,
    cancelWindowStartFrame: 6,
    damage: 260,
    poiseDamage: 40,
    hitType: 'Light Slash',
    description: 'Follow-up diagonal slash pushing target back slightly.',
    nextStates: ['heavy_finisher', 'dodge_cancel']
  },
  heavy_finisher: {
    id: 'heavy_finisher',
    name: 'HEAVY_FINISHER (SEVER BLADE)',
    inputTrigger: 'K (Heavy)',
    startupFrames: 12,
    activeFrames: 6,
    recoveryFrames: 16,
    cancelWindowStartFrame: 14,
    damage: 650,
    poiseDamage: 120,
    hitType: 'Heavy Cleave',
    description: 'Devastating overhead attack causing armor break and target launch state.',
    nextStates: ['idle']
  },
  parry: {
    id: 'parry',
    name: 'DEFENSIVE_PARRY (AEGIS REFLEX)',
    inputTrigger: 'L (Parry)',
    startupFrames: 2,
    activeFrames: 8,
    recoveryFrames: 12,
    cancelWindowStartFrame: 4,
    damage: 0,
    poiseDamage: 200,
    hitType: 'Parry Counter',
    description: 'Frame 2 active parry block. Succesful trigger instantly forces attacker into Guard Break.',
    nextStates: ['parry_counter']
  },
  parry_counter: {
    id: 'parry_counter',
    name: 'COUNTER_RIPOSTE',
    inputTrigger: 'AUTO_TRIGGER',
    startupFrames: 3,
    activeFrames: 5,
    recoveryFrames: 6,
    cancelWindowStartFrame: 4,
    damage: 820,
    poiseDamage: 300,
    hitType: 'Finisher',
    description: 'Guaranteed execution counter deal critical damage to staggered enemy.',
    nextStates: ['idle']
  },
  dodge_cancel: {
    id: 'dodge_cancel',
    name: 'PHASE_SHIFT_DODGE',
    inputTrigger: 'Space (Dodge)',
    startupFrames: 1,
    activeFrames: 10,
    recoveryFrames: 4,
    cancelWindowStartFrame: 2,
    damage: 0,
    poiseDamage: 0,
    hitType: 'Light Slash',
    description: 'Invulnerability frame (i-frame) dash maneuver canceling active attack recovery.',
    nextStates: ['idle', 'light_1']
  }
};

export const PROJECTS: Project[] = [
  {
    id: 'project-vanguard',
    title: 'PROJECT VANGUARD',
    subtitle: 'AAA Dynamic Melee Combat Engine in UE5 C++',
    category: 'action-combat',
    engine: 'Unreal Engine 5 (C++)',
    role: 'Lead Gameplay Systems Engineer',
    year: '2024',
    summary: 'High-response melee combat system featuring deterministic frame buffering, dynamic hit-stop micro-freezes, spatial capsule sweeps, and custom poise/posture break mechanics.',
    detailedDescription: 'Project Vanguard was built from the ground up in Unreal Engine 5 C++ to achieve tight, responsive melee combat comparable to Devil May Cry and Sekiro. The core architecture uses an event-driven Gameplay Ability System (GAS) hybrid coupled with custom animation montage frame notifiers and deterministic input buffering.',
    bannerImage: 'https://images.unsplash.com/photo-1542751371-adc38448a05e?q=80&w=1200&auto=format&fit=crop',
    accentColor: 'cyan',
    tags: ['UE5 C++', 'Combat State Machine', 'Hit-Stop Interpolation', 'Spatial Capsule Sweeps', 'GAS Hybrid'],
    metrics: [
      { label: 'INPUT LATENCY', value: '8.3ms', subtext: 'Sub-frame input processing' },
      { label: 'HIT DETECTION COST', value: '0.12ms', subtext: 'Multi-target collision sweeps' },
      { label: 'COMBO BRANCH STATES', value: '48+', subtext: 'Fluid animation transitions' }
    ],
    features: [
      'Deterministic Input Buffer Queue (0-300ms window with priority override)',
      'Dynamic Hit-Stop & Camera Shake Interpolation based on strike impact vectors',
      'Frame-accurate Hitbox Capsules attached to Weapon Sockets with motion vector compensation',
      'Poise & Stagger System with directional hit reactions and Guard Break execution triggers',
      'Motion Matching and Blend Spaces for seamless directional locomotion during combat locks'
    ],
    architectureHighlights: [
      {
        title: 'Componentized State Handler',
        description: 'Decoupled UCombatComponent handling input queueing, stamina check, hit registration, and animation notifications without polluting ACharacter base class.'
      },
      {
        title: 'Collision Sweep Pipeline',
        description: 'Replaced physics overlaps with frame-to-frame socket trajectory sweeps (UWorld::SweepMultiByChannel) eliminating phantom misses at high framerates.'
      }
    ],
    codeSnippet: {
      title: 'VanguardCombatComponent.cpp - Hitbox Sweep & Frame Cancel',
      language: 'cpp',
      description: 'C++ Socket Trajectory Sweep algorithm ensuring zero missed hits during high-velocity weapon swings.',
      code: `// VanguardCombatComponent.cpp - Frame-Accurate Socket Trajectory Sweep
#include "VanguardCombatComponent.h"
#include "Engine/OverlapResult.h"
#include "Kismet/KismetSystemLibrary.h"

void UVanguardCombatComponent::PerformWeaponTraceSweep(const FWeaponTraceData& TraceData)
{
    AActor* OwnerActor = GetOwner();
    if (!OwnerActor || !TraceData.WeaponMesh) return;

    const FVector PrevTip = TraceData.LastTipLocation;
    const FVector CurrTip = TraceData.WeaponMesh->GetSocketLocation(TraceData.TipSocketName);
    const FVector PrevBase = TraceData.LastBaseLocation;
    const FVector CurrBase = TraceData.WeaponMesh->GetSocketLocation(TraceData.BaseSocketName);

    TArray<FHitResult> OutHits;
    FCollisionQueryParams QueryParams;
    QueryParams.AddIgnoredActor(OwnerActor);
    QueryParams.bTraceComplex = false;

    const FQuat SweepRotation = OwnerActor->GetActorQuat();
    const FCollisionShape CapsuleShape = FCollisionShape::MakeCapsule(TraceData.BladeRadius, FVector::Distance(CurrTip, CurrBase) * 0.5f);
    const FVector CenterPoint = (CurrTip + CurrBase) * 0.5f;

    bool bHit = GetWorld()->SweepMultiByChannel(
        OutHits,
        CenterPoint,
        CenterPoint + (CurrTip - PrevTip),
        SweepRotation,
        ECC_GameTraceChannel1,
        CapsuleShape,
        QueryParams
    );

    if (bHit)
    {
        for (const FHitResult& Hit : OutHits)
        {
            AActor* HitActor = Hit.GetActor();
            if (HitActor && !AlreadyHitActors.Contains(HitActor))
            {
                AlreadyHitActors.Add(HitActor);
                ProcessImpact(HitActor, Hit, TraceData.CurrentAttackData);
            }
        }
    }

    TraceData.LastTipLocation = CurrTip;
    TraceData.LastBaseLocation = CurrBase;
}`
    }
  },
  {
    id: 'chronos-engine',
    title: 'CHRONOS ACTION ENGINE',
    subtitle: 'Custom C# Custom 3D Action Engine & Physics Pipeline',
    category: 'custom-engine',
    engine: 'Custom C# Engine / OpenTK / Silk.NET',
    role: 'Engine & Architecture Developer',
    year: '2023',
    summary: 'A standalone data-driven 3D action engine engineered for ultra-fast frame rates, sub-millisecond collision response, and a modular entity-component system (ECS).',
    detailedDescription: 'Built without third-party game engines to master low-level architecture, Chronos Engine features custom spatial hash partitioning, custom math libraries, a frame-perfect command-pattern input recorder, and custom shader pipelines.',
    bannerImage: 'https://images.unsplash.com/photo-1550745165-9bc0b252726f?q=80&w=1200&auto=format&fit=crop',
    accentColor: 'purple',
    tags: ['Custom Engine', 'C# / OpenTK', 'Spatial Hashing', 'Command Pattern', 'Direct Physics'],
    metrics: [
      { label: 'AVERAGE FPS', value: '450+ FPS', subtext: 'At 1440p High Resolution' },
      { label: 'SPATIAL HASH LOOKUP', value: '0.04ms', subtext: '5,000 rigid entities' },
      { label: 'MEMORY FOOTPRINT', value: '< 180 MB', subtext: 'Zero GC allocations per frame' }
    ],
    features: [
      'Custom Lockless Entity Component Architecture with Memory Pool allocation',
      'Spatial Hashing 3D Grid for O(1) collision detection query overhead',
      'Replay & Input Rewind System using serialized Command Queue pattern',
      'Data-Driven Ability Configuration via JSON schema hot-reloading',
      'Custom Forward+ Shader Pipeline with dynamic point light clustering'
    ],
    architectureHighlights: [
      {
        title: 'Zero-Allocation Garbage Collection Loop',
        description: 'Utilized Struct Arrays and Span<T> memory buffer pools to eliminate GC spikes during heavy physics interactions.'
      },
      {
        title: 'Command Pattern Input Replay',
        description: 'Input states are buffered into compact bitmasks, allowing instant frame rewind and fighting game netcode determinism.'
      }
    ],
    codeSnippet: {
      title: 'SpatialHashGrid.cs - O(1) Collision Spatial Partitioning',
      language: 'csharp',
      description: 'High-performance 3D Spatial Grid for broadphase collision checks eliminating N^2 complexity.',
      code: `// SpatialHashGrid.cs - Fast 3D Hash Partitioning
using System;
using System.Collections.Generic;
using System.Numerics;

public class SpatialHashGrid<T> where T : class
{
    private readonly float cellSize;
    private readonly Dictionary<long, List<T>> grid;
    private const int HashPrime1 = 73856093;
    private const int HashPrime2 = 19349663;
    private const int HashPrime3 = 83492791;

    public SpatialHashGrid(float cellSize, int initialCapacity = 4096)
    {
        this.cellSize = cellSize;
        this.grid = new Dictionary<long, List<T>>(initialCapacity);
    }

    [System.Runtime.CompilerServices.MethodImpl(System.Runtime.CompilerServices.MethodImplOptions.AggressiveInlining)]
    private long GetHashKey(int x, int y, int z)
    {
        unchecked
        {
            return (long)((x * HashPrime1) ^ (y * HashPrime2) ^ (z * HashPrime3));
        }
    }

    public void Insert(Vector3 min, Vector3 max, T obj)
    {
        int minX = (int)MathF.Floor(min.X / cellSize);
        int minY = (int)MathF.Floor(min.Y / cellSize);
        int minZ = (int)MathF.Floor(min.Z / cellSize);
        int maxX = (int)MathF.Floor(max.X / cellSize);
        int maxY = (int)MathF.Floor(max.Y / cellSize);
        int maxZ = (int)MathF.Floor(max.Z / cellSize);

        for (int x = minX; x <= maxX; x++)
        {
            for (int y = minY; y <= maxY; y++)
            {
                for (int z = minZ; z <= maxZ; z++)
                {
                    long key = GetHashKey(x, y, z);
                    if (!grid.TryGetValue(key, out var cellList))
                    {
                        cellList = new List<T>(8);
                        grid[key] = cellList;
                    }
                    cellList.Add(obj);
                }
            }
        }
    }
}`
    }
  },
  {
    id: 'aegis-ai-system',
    title: 'AEGIS TACTICAL AI ENGINE',
    subtitle: 'Utility AI & Squad Flanking Framework for Shooter/Action Games',
    category: 'ai-physics',
    engine: 'Unity C# / DOTS Compatible',
    role: 'AI & Combat Programmer',
    year: '2024',
    summary: 'A tactical AI framework implementing Utility Scoring, Cover Evaluation Sweeps, and Dynamic Squad Role Distribution for aggressive NPC flank behavior.',
    detailedDescription: 'Aegis AI delivers lifelike combat behaviors where enemies evaluate combat options in real time using multi-factor utility functions rather than static decision trees. Squads communicate cover density and crossfire lanes dynamically.',
    bannerImage: 'https://images.unsplash.com/photo-1511512578047-dfb367046420?q=80&w=1200&auto=format&fit=crop',
    accentColor: 'yellow',
    tags: ['Utility AI', 'Squad Tactical Behavior', 'Cover Scoring', 'NavMesh Raycasting'],
    metrics: [
      { label: 'EVALUATED AI AGENTS', value: '150+', subtext: 'Simultaneous 60 FPS combatants' },
      { label: 'UTILITY SCORE TICK', value: '0.08ms', subtext: 'Per agent decision tree tick' },
      { label: 'FLANKING EFFICIENCY', value: '+85%', subtext: 'Tactical cover utilization' }
    ],
    features: [
      'Multi-Criteria Utility Evaluator (Score = Distance * LineOfSight * Suppression * FlankAngle)',
      'Dynamic Squad Director distributing roles: Suppressor, Flanker, Rusher, Support',
      'Cover Point Quality Sweeper evaluating cover height, bullet penetration, and escape routes',
      'Perception Model with Raycast Vision Cones, Sound Radius Audition, and Memory Decay'
    ],
    architectureHighlights: [
      {
        title: 'Utility Curves over Behavior Trees',
        description: 'Replaced rigid BT branch transitions with continuous mathematical curve evaluation, preventing AI oscillation between cover states.'
      },
      {
        title: 'Async Job System Threading',
        description: 'Offloaded cover evaluation raycasts to Unity C# Job System with NativeArray memory layouts.'
      }
    ],
    codeSnippet: {
      title: 'CoverEvaluatorUtility.cs - Multi-Factor Cover Point Evaluator',
      language: 'csharp',
      description: 'Utility AI algorithm for rating cover spots based on threat position, flank angle, and safety score.',
      code: `// CoverEvaluatorUtility.cs - Real-time Tactical Cover Point Evaluator
using UnityEngine;

public static class CoverEvaluatorUtility
{
    public static float EvaluateCoverSpot(
        Vector3 coverPos, 
        Vector3 threatPos, 
        Vector3 agentPos, 
        Vector3 coverNormal,
        float maxDistance)
    {
        float distToCover = Vector3.Distance(agentPos, coverPos);
        float distanceFactor = 1.0f - Mathf.Clamp01(distToCover / maxDistance);

        Vector3 dirToThreat = (threatPos - coverPos).normalized;
        float dotProduct = Vector3.Dot(coverNormal, dirToThreat);
        float protectionFactor = Mathf.Clamp01(dotProduct);

        bool bBlocksRay = Physics.Linecast(
            coverPos + Vector3.up * 1.2f, 
            threatPos + Vector3.up * 1.2f, 
            LayerMask.GetMask("Obstacle")
        );
        float losFactor = bBlocksRay ? 1.0f : 0.05f;

        float totalScore = (protectionFactor * 0.45f) + (distanceFactor * 0.30f) + (losFactor * 0.25f);
        return Mathf.Clamp01(totalScore);
    }
}`
    }
  },
  {
    id: 'apex-shaders',
    title: 'APEX SHADER & IMPACT GRAPH',
    subtitle: 'Real-time Dynamic Weapon Damage, Shield Hex & Particle Shaders',
    category: 'shaders-vfx',
    engine: 'HLSL / Unreal Shader Graph',
    role: 'Tech Artist & Shader Engineer',
    year: '2024',
    summary: 'A procedural shader collection for dynamic weapon slashing trails, procedural impact hit-ripples, energy shield hex distortion, and directional mesh dismemberment burns.',
    detailedDescription: 'Built to enhance combat readability, this shader suite computes procedural impact ripples at exact collision contact points using vertex displacement and custom distance fields.',
    bannerImage: 'https://images.unsplash.com/photo-1579546929518-9e396f3cc809?q=80&w=1200&auto=format&fit=crop',
    accentColor: 'pink',
    tags: ['HLSL', 'Unreal Shader Graph', 'Procedural Impact', 'Shield Distortion', 'VFX Pipeline'],
    metrics: [
      { label: 'INSTRUCTION COUNT', value: '112 ALU', subtext: 'Optimized for mobile & console' },
      { label: 'SHIELD RIPPLE COUNT', value: '8 Hits', subtext: 'Simultaneous impact points' },
      { label: 'RENDER PASS', value: 'Forward+', subtext: 'Zero depth buffer artifacts' }
    ],
    features: [
      'Multi-Impact Hexagonal Forcefield Shader with procedural ripple wave propagation',
      'Dynamic Armor Damage Wear driven by UV Mask Painting and Normal Blend',
      'Procedural Arc Blade Slashing Trail with customizable color gradient noise curves',
      'Vertex Displacement Dissolve Shaders for enemy death disintegration effects'
    ],
    architectureHighlights: [
      {
        title: 'Array-Based Impact Spheres',
        description: 'Passed array of Vector4 impact origins and timestamps into HLSL material parameters for dynamic multi-bullet shield ripples.'
      }
    ],
    codeSnippet: {
      title: 'HexShieldImpact.hlsl - Procedural Multi-Point Forcefield Ripple Shader',
      language: 'hlsl',
      description: 'Custom HLSL function calculating distance wave distortion from hit coordinates on hex shield meshes.',
      code: `// HexShieldImpact.hlsl - Multi-Point Impact Wave Displacement
#ifndef HEX_SHIELD_IMPACT_INCLUDED
#define HEX_SHIELD_IMPACT_INCLUDED

void CalculateShieldRipple_float(
    float3 WorldPos,
    float3 HitOrigin,
    float HitTimestamp,
    float CurrentTime,
    float RippleSpeed,
    float RippleFrequency,
    out float RippleIntensity)
{
    float dist = distance(WorldPos, HitOrigin);
    float elapsedTime = CurrentTime - HitTimestamp;

    if (elapsedTime < 0.0 || elapsedTime > 1.5)
    {
        RippleIntensity = 0.0;
        return;
    }

    float wavefront = elapsedTime * RippleSpeed;
    float waveDist = abs(dist - wavefront);

    float fadeOut = saturate(1.0 - (elapsedTime / 1.5));
    float pulse = sin(waveDist * RippleFrequency) * saturate(1.0 - waveDist * 2.0);

    RippleIntensity = max(0.0, pulse * fadeOut);
}

#endif`
    }
  }
];

export const TECH_STACK: TechCategory[] = [
  {
    id: 'core-engines',
    title: 'ENGINES & CORE ARCHITECTURE',
    subtitle: 'Low-level C++, engine internals, and game loop orchestration',
    icon: 'Cpu',
    color: 'cyan',
    items: [
      {
        name: 'Unreal Engine 5 (C++)',
        level: 95,
        experienceYears: '5+ Years',
        tag: 'Primary Engine',
        highlights: ['GAS (Gameplay Ability System)', 'Custom AnimNotifies & Montages', 'UObject / GC Memory Management', 'Async Task Graph']
      },
      {
        name: 'Custom C# Engine Architecture',
        level: 90,
        experienceYears: '3 Years',
        tag: 'Custom Engine',
        highlights: ['OpenTK / Silk.NET Frameworks', 'Entity Component Architecture (ECS)', 'Spatial Hash 3D Grids', 'Custom Fixed Timestep Loops']
      },
      {
        name: 'Unity (C# & DOTS)',
        level: 88,
        experienceYears: '4 Years',
        tag: 'Secondary Engine',
        highlights: ['Burst Compiler & Job System', 'Scriptable Object Data Systems', 'Custom Physics Overlaps', 'Input System API']
      }
    ]
  },
  {
    id: 'gameplay-systems',
    title: 'COMBAT & GAMEPLAY SYSTEMS',
    subtitle: 'Combat state machines, input buffering, and dynamic combat design',
    icon: 'Swords',
    color: 'purple',
    items: [
      {
        name: 'Deterministic Input Buffering',
        level: 96,
        experienceYears: '4 Years',
        tag: 'Combat Tech',
        highlights: ['Frame-accurate priority queue', 'Cancel window execution', 'Input remapping & netcode readiness', 'Buffer state overrides']
      },
      {
        name: 'Combat State Machines',
        level: 98,
        experienceYears: '5 Years',
        tag: 'System Design',
        highlights: ['Hierarchical Finite State Machines', 'Poise & Stagger System', 'Directional Hit Reactions', 'Guard Break & Finishers']
      },
      {
        name: 'Hitbox & Spatial Collision',
        level: 92,
        experienceYears: '4 Years',
        tag: 'Physics Collision',
        highlights: ['Continuous Capsule Sweeps', 'Socket-to-Socket Motion Tracing', 'Hurtbox Prioritization', 'Zero-Lag Overlap Caching']
      }
    ]
  },
  {
    id: 'ai-shaders',
    title: 'AI, PHYSICS & SHADERS',
    subtitle: 'Tactical behaviors, pathfinding, and dynamic shader effects',
    icon: 'Zap',
    color: 'yellow',
    items: [
      {
        name: 'Tactical Utility AI & Squads',
        level: 90,
        experienceYears: '3 Years',
        tag: 'AI Behavior',
        highlights: ['Continuous Utility Score Curves', 'Dynamic Cover Evaluation Sweeps', 'Squad Flanking & Suppression', 'Perception Vision Cones']
      },
      {
        name: 'Shaders & VFX Pipeline',
        level: 85,
        experienceYears: '3 Years',
        tag: 'Tech Art',
        highlights: ['Unreal Shader Graph & HLSL', 'Procedural Impact Ripples', 'Weapon Slashing Mesh Trails', 'Dissolve & Hex Distortion']
      }
    ]
  }
];

export const CODE_PATTERNS: CodePattern[] = [
  {
    id: 'state-machine',
    title: 'Hierarchical Combat State Machine',
    patternName: 'State Pattern + Callback Listeners',
    language: 'cpp',
    engine: 'Unreal Engine 5',
    summary: 'A robust C++ state machine controlling combat stances, animation state transitions, cancel windows, and hitbox activations with zero frame delays.',
    code: `// CombatStateMachine.h - Modular State Handler
#pragma once

#include "CoreMinimal.h"
#include "UObject/NoExportTypes.h"
#include "CombatStateMachine.generated.h"

UENUM(BlueprintType)
enum class ECombatState : uint8
{
    Idle            UMETA(DisplayName = "Idle"),
    Startup         UMETA(DisplayName = "Startup"),
    ActiveHitbox    UMETA(DisplayName = "Active Hitbox"),
    CancelWindow    UMETA(DisplayName = "Cancel Window"),
    Recovery        UMETA(DisplayName = "Recovery"),
    Staggered       UMETA(DisplayName = "Staggered")
};

DECLARE_DYNAMIC_MULTICAST_DELEGATE_TwoParams(FOnStateChanged, ECombatState, OldState, ECombatState, NewState);

UCLASS(BlueprintType, Blueprintable)
class VANGUARD_API UCombatStateMachine : public UObject
{
    GENERATED_BODY()

public:
    UCombatStateMachine();

    void TickState(float DeltaTime);
    bool TransitionTo(ECombatState NewState);
    
    FORCEINLINE ECombatState GetCurrentState() const { return CurrentState; }
    FORCEINLINE bool IsCancelable() const { return CurrentState == ECombatState::CancelWindow; }

    UPROPERTY(BlueprintAssignable, Category = "Combat State")
    FOnStateChanged OnStateChanged;

private:
    ECombatState CurrentState = ECombatState::Idle;
    float StateTimer = 0.0f;
};`,
    architectureBreakdown: [
      'Encapsulates state transitions to prevent invalid combo jumps (e.g. Recovery straight to Heavy Finisher without Cancel Window).',
      'Exposes BlueprintAssignable delegates allowing Audio & Particle VFX listeners to bind effortlessly.',
      'Supports frame-level precision for fighting game or hardcore Action RPG mechanics.'
    ]
  },
  {
    id: 'input-buffer',
    title: 'Frame-Accurate Input Queue',
    patternName: 'Ring Buffer + Command Pattern',
    language: 'csharp',
    engine: 'Custom Engine',
    summary: 'Queues player button presses into a frame-stamped ring buffer, guaranteeing frame-perfect execution of buffered attacks even if pressed slightly before recovery finishes.',
    code: `// InputBufferQueue.cs - Deterministic Command Ring Buffer
using System.Collections.Generic;

public enum CombatCommand { None, LightAttack, HeavyAttack, Parry, Dodge }

public struct BufferedInput
{
    public CombatCommand Command;
    public float Timestamp;
    public bool Executed;
}

public class InputBufferQueue
{
    private readonly Queue<BufferedInput> buffer = new Queue<BufferedInput>(16);
    private readonly float maxBufferWindowSeconds;

    public InputBufferQueue(float maxWindowSeconds = 0.25f)
    {
        maxBufferWindowSeconds = maxWindowSeconds;
    }

    public void EnqueueInput(CombatCommand cmd, float currentTime)
    {
        buffer.Enqueue(new BufferedInput { Command = cmd, Timestamp = currentTime, Executed = false });
    }

    public bool TryConsumeInput(float currentTime, out CombatCommand validCommand)
    {
        validCommand = CombatCommand.None;

        while (buffer.Count > 0)
        {
            var peek = buffer.Peek();
            if (currentTime - peek.Timestamp > maxBufferWindowSeconds)
            {
                buffer.Dequeue();
                continue;
            }

            validCommand = buffer.Dequeue().Command;
            return true;
        }

        return false;
    }
}`,
    architectureBreakdown: [
      'Prevents dropped player inputs by caching keypresses up to 250ms prior to animation availability.',
      'Automatically purges stale inputs to avoid accidental delayed attacks.',
      'Lightweight allocation-free struct design for high FPS execution.'
    ]
  },
  {
    id: 'hitbox-sweep',
    title: 'Continuous Motion Hitbox Sweep',
    patternName: 'CCD Capsule Trajectory Sweep',
    language: 'cpp',
    engine: 'Unreal Engine 5',
    summary: 'Prevents fast weapon meshes from phasing through enemies at low framerates by performing continuous capsule sweeps between previous and current socket positions.',
    code: `// WeaponSweepSystem.cpp - Multi-Socket Trajectory Interpolation
void UWeaponSweepSystem::UpdateWeaponSweep(float DeltaTime)
{
    if (!bIsSweepActive || !WeaponMesh) return;

    FVector CurrentBase = WeaponMesh->GetSocketLocation(BaseSocketName);
    FVector CurrentTip = WeaponMesh->GetSocketLocation(TipSocketName);

    FVector MidPoint = (CurrentBase + CurrentTip) * 0.5f;
    FVector PreviousMidPoint = (PreviousBaseLocation + PreviousTipLocation) * 0.5f;

    TArray<FHitResult> SweepHits;
    FCollisionQueryParams Params;
    Params.AddIgnoredActor(GetOwner());

    FCollisionShape SweepCapsule = FCollisionShape::MakeCapsule(BladeWidth, FVector::Distance(CurrentTip, CurrentBase) * 0.5f);

    bool bHitOccurred = GetWorld()->SweepMultiByChannel(
        SweepHits,
        PreviousMidPoint,
        MidPoint,
        GetOwner()->GetActorQuat(),
        ECC_GameTraceChannel1,
        SweepCapsule,
        Params
    );

    if (bHitOccurred)
    {
        OnHitDetected(SweepHits);
    }

    PreviousBaseLocation = CurrentBase;
    PreviousTipLocation = CurrentTip;
}`,
    architectureBreakdown: [
      'Eliminates collision tunnelling (weapon slicing through enemy without registering hit).',
      'Maintains array of unique hit targets per attack animation cycle to avoid double-hitting the same target.',
      'Highly optimized for multi-enemy hack-and-slash games.'
    ]
  }
];
